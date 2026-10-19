#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MASTER_ANALYSIS JSON으로 00~04 또는 V2 00~05 HWPX 분석 문서를 생성한다."""

import argparse
import copy
import json
import math
import os
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from lxml import etree

from hwpx_logic_embedder import (
    add_png_resource,
    remove_logic_elements,
    remove_placeholder_resource,
    replace_logic_picture,
    validate_hwpx_image_references,
)
from logic_visualizer import render_logic_visualization, validate_logic_visualization

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
NS = {"hp": HP_NS, "hs": HS_NS, "hh": HH_NS}

PASSAGE_REQUIRED_KEYS = [
    "번호",
    "전체_내용",
    "배경_지식",
    "소재",
    "주제",
    "요지",
    "제목",
    "한_문장_요약",
    "주제문_번호",
    "지문",
    "어휘",
]

SCALAR_STRING_KEYS = [
    "번호",
    "전체_내용",
    "주제",
    "요지",
    "제목",
    "한_문장_요약",
    "주제문_번호",
]

AUTO_FIT_SENTENCE_ROW_HEIGHT = "1"
SENTENCE_PAGE_BREAK_SECTION_NUMBERS = {"03", "04"}

LEADING_MARKER_RE = re.compile(r"^([^A-Za-z0-9가-힣\[\(]+\s*)")

def _looks_like_analysis_header_row(row):
    cells = child_cells(row)
    texts = [_normalize_header_text(cell_text(cell)) for cell in cells[:2]]
    if len(texts) < 2:
        return False
    return texts[0] in {"구분", "항목"} and texts[1] in {"내용", "text", "value"}


def _looks_like_sentence_header_row(row):
    texts = [_normalize_header_text(cell_text(cell)) for cell in child_cells(row)]
    joined = " ".join(texts)
    if not joined.strip():
        return False
    header_tokens = ["문장", "번호", "지문분석", "본문", "영어", "직독직해", "해석", "한국어"]
    return any(token in joined for token in header_tokens)


def _table_data_rows(tbl, header_checker=None):
    rows = child_rows(tbl)
    if not rows:
        return [], False
    has_header = bool(header_checker and header_checker(rows[0]))
    return (rows[1:] if has_header else rows), has_header



def hp(tag: str) -> str:
    return f"{{{HP_NS}}}{tag}"


def child_rows(tbl):
    return [c for c in tbl if c.tag == hp("tr")]


def child_cells(row):
    return [c for c in row if c.tag == hp("tc")]


def first_child(parent, tag_name: str):
    return parent.find(f"./{hp(tag_name)}")


def ensure_child(parent, tag_name: str):
    child = first_child(parent, tag_name)
    if child is None:
        child = etree.SubElement(parent, hp(tag_name))
    return child


def get_sublist(cell):
    sub = cell.find(f"./{hp('subList')}")
    if sub is None:
        sub = etree.Element(hp("subList"))
        sub.set("id", "")
        sub.set("textDirection", "HORIZONTAL")
        sub.set("lineWrap", "BREAK")
        sub.set("vertAlign", "TOP")
        sub.set("linkListIDRef", "0")
        sub.set("linkListNextIDRef", "0")
        sub.set("textWidth", "0")
        sub.set("textHeight", "0")
        sub.set("hasTextRef", "0")
        sub.set("hasNumRef", "0")
        cell.insert(0, sub)
    return sub


def cell_paras(cell):
    sub = get_sublist(cell)
    return [c for c in sub if c.tag == hp("p")]


def para_runs(para):
    return para.findall(f"./{hp('run')}")


def clear_linesegarray(para):
    for el in para.findall(f"./{hp('linesegarray')}"):
        para.remove(el)


def ensure_para_with_text(para, text=""):
    runs = para_runs(para)
    if runs:
        run = runs[0]
    else:
        run = etree.SubElement(para, hp("run"))
        run.set("charPrIDRef", "18")
    t = run.find(f"./{hp('t')}")
    if t is None:
        t = etree.SubElement(run, hp("t"))
    t.text = text
    for extra in para_runs(para)[1:]:
        para.remove(extra)
    clear_linesegarray(para)
    return para


def make_para_like(base_para=None, text=""):
    if base_para is not None:
        para = copy.deepcopy(base_para)
        for child in list(para):
            if child.tag != hp("run"):
                para.remove(child)
        ensure_para_with_text(para, text)
        return para

    para = etree.Element(hp("p"))
    para.set("id", "2147483648")
    para.set("paraPrIDRef", "16")
    para.set("styleIDRef", "0")
    para.set("pageBreak", "0")
    para.set("columnBreak", "0")
    para.set("merged", "0")
    ensure_para_with_text(para, text)
    return para


def ensure_cell_paras(cell, n):
    sub = get_sublist(cell)
    paras = cell_paras(cell)
    base = paras[0] if paras else None
    while len(paras) < n:
        sub.append(make_para_like(base, ""))
        paras = cell_paras(cell)
    return paras


def replace_cell_text(cell, text):
    paras = ensure_cell_paras(cell, 1)
    ensure_para_with_text(paras[0], text)
    sub = get_sublist(cell)
    for p in cell_paras(cell)[1:]:
        sub.remove(p)


def replace_cell_text_with_trailing_blank_line(cell, text):
    paras = ensure_cell_paras(cell, 2)
    text_template, blank_template = paras[0], paras[1]
    sub = get_sublist(cell)
    for p in cell_paras(cell):
        sub.remove(p)
    for line in str(text).split("\n"):
        sub.append(make_para_like(text_template, line))
    sub.append(make_para_like(blank_template, ""))



ENGLISH_PARENTHESIS_RE = re.compile(r"\([^()가-힣]*[A-Za-z][^()가-힣]*\)")


def _style_parenthesized_english(para, text, english_charpr):
    """Keep the template's blue English runs inside Korean analysis text."""
    if not english_charpr or not re.search(r"[가-힣]", text):
        return
    pieces = ENGLISH_PARENTHESIS_RE.split(text)
    accents = ENGLISH_PARENTHESIS_RE.findall(text)
    if not accents:
        return

    base_run = para_runs(para)[0]
    base_style = base_run.get("charPrIDRef")
    for run in para_runs(para):
        para.remove(run)
    for index, piece in enumerate(pieces):
        for segment, charpr in ((piece, base_style),
                                (accents[index], english_charpr) if index < len(accents) else ("", base_style)):
            if not segment:
                continue
            run = copy.deepcopy(base_run)
            if charpr:
                run.set("charPrIDRef", charpr)
            for child in list(run):
                run.remove(child)
            span = etree.SubElement(run, hp("t"))
            span.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            span.text = segment
            para.append(run)


def replace_cell_multitext(cell, lines, english_charpr=None):
    if not lines:
        replace_cell_text(cell, "")
        return

    lines = [str(line) for line in lines if str(line).strip()]
    if not lines:
        replace_cell_text(cell, "")
        return

    existing_paras = cell_paras(cell)
    templates = existing_paras if existing_paras else [None]
    sub = get_sublist(cell)

    for p in existing_paras:
        sub.remove(p)

    for i, line in enumerate(lines):
        template_para = templates[i] if i < len(templates) else templates[-1]
        new_para = make_para_like(template_para, line)
        _style_parenthesized_english(new_para, line, english_charpr)
        if i == 0:
            new_para.set("pageBreak", "0")
        sub.append(new_para)


def patch_header(tbl, c):
    rows = child_rows(tbl)
    if not rows:
        return
    cells = child_cells(rows[0])
    if len(cells) >= 2:
        replace_cell_text(cells[1], str(c["번호"]))


def patch_page_header(elements, school="", range_text=""):
    if not school and not range_text:
        return

    headers = [header for element in elements for header in element.findall(".//hp:header", NS)]
    if not headers:
        raise ValueError("HWPX 템플릿에서 머리말 객체를 찾지 못했습니다.")

    for header in headers:
        paragraphs = header.findall(".//hp:p", NS)
        for value, label, para_pr_id in (
            (school, "학교", "2"),
            (range_text, "범위", "3"),
        ):
            if not value:
                continue
            matches = [
                paragraph for paragraph in paragraphs
                if paragraph.get("paraPrIDRef") == para_pr_id
                and paragraph.find("./hp:run/hp:t", NS) is not None
            ]
            if len(matches) != 1:
                raise ValueError(f"HWPX 템플릿의 {label} 머리말 위치를 하나로 식별하지 못했습니다.")
            ensure_para_with_text(matches[0], value)


def patch_summary(tbl, c):
    rows = child_rows(tbl)
    if not rows:
        return
    cells = child_cells(rows[0])
    if cells:
        replace_cell_text(cells[0], c["전체_내용"])



def _extract_leading_marker(text):
    if not text:
        return ""
    match = LEADING_MARKER_RE.match(text)
    return match.group(1) if match else ""


def _set_bg(cell, title, body):
    existing_paras = cell_paras(cell)
    title_template = existing_paras[0] if len(existing_paras) >= 1 else None
    body_template = existing_paras[1] if len(existing_paras) >= 2 else title_template

    title_template_text = ""
    if title_template is not None:
        title_template_text = "".join((t.text or "") for t in title_template.findall(f".//{hp('t')}"))
    marker = _extract_leading_marker(title_template_text)

    title_text = str(title)
    if marker and not title_text.startswith(marker):
        title_text = f"{marker}{title_text}"

    sub = get_sublist(cell)
    for p in cell_paras(cell):
        sub.remove(p)

    sub.append(make_para_like(title_template, title_text))
    sub.append(make_para_like(body_template, str(body)))


def _clear_bg(cell):
    existing_paras = cell_paras(cell)
    title_template = existing_paras[0] if len(existing_paras) >= 1 else None
    body_template = existing_paras[1] if len(existing_paras) >= 2 else title_template

    sub = get_sublist(cell)
    for p in cell_paras(cell):
        sub.remove(p)

    sub.append(make_para_like(title_template, ""))
    sub.append(make_para_like(body_template, ""))


def bg_slot_indices_for_row(row):
    count = len(child_cells(row))
    if count >= 3:
        return [0, 2]
    if count == 2:
        return [0, 1]
    if count == 1:
        return [0]
    return []


def patch_background(tbl, c):
    terms = c.get("배경_지식", [])
    rows = child_rows(tbl)
    if not rows:
        return

    first_slots = bg_slot_indices_for_row(rows[0])
    slots_per_row = max(1, len(first_slots))
    needed_rows = max(1, math.ceil(len(terms) / slots_per_row)) if terms else 1

    while len(child_rows(tbl)) > needed_rows:
        tbl.remove(child_rows(tbl)[-1])
    while len(child_rows(tbl)) < needed_rows:
        tbl.append(copy.deepcopy(child_rows(tbl)[-1]))

    rows = child_rows(tbl)
    term_idx = 0
    for row in rows:
        slots = bg_slot_indices_for_row(row)
        cells = child_cells(row)
        for slot in slots:
            if slot >= len(cells):
                continue
            cell = cells[slot]
            if term_idx < len(terms):
                _set_bg(cell, terms[term_idx]["제목"], terms[term_idx]["내용"])
                term_idx += 1
            else:
                _clear_bg(cell)



def patch_analysis(tbl, c):
    rows, has_header = _table_data_rows(tbl, _looks_like_analysis_header_row)
    start_idx = 1 if has_header else 0
    english_charpr = None
    for row in rows[start_idx + 1:]:
        cells = child_cells(row)
        if len(cells) < 2:
            continue
        for para in cell_paras(cells[1]):
            runs = para_runs(para)
            default_style = runs[0].get("charPrIDRef") if runs else None
            for run in runs[1:]:
                text = "".join(t.text or "" for t in run.findall(f"./{hp('t')}"))
                style = run.get("charPrIDRef")
                if style != default_style and ENGLISH_PARENTHESIS_RE.fullmatch(text):
                    english_charpr = style
                    break
            if english_charpr:
                break
        if english_charpr:
            break
    row_map = [
        (start_idx + 0, c.get("소재", [])),
        (start_idx + 1, [c.get("주제", "")]),
        (start_idx + 2, [c.get("요지", "")]),
        (start_idx + 3, [c.get("제목", "")]),
        (start_idx + 4, [c.get("한_문장_요약", "")]),
    ]
    all_rows = child_rows(tbl)
    for ri, lines in row_map:
        if ri >= len(all_rows):
            continue
        cells = child_cells(all_rows[ri])
        if len(cells) >= 2:
            replace_cell_multitext(cells[1], lines, english_charpr if ri > start_idx else None)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def cell_text(cell):
    return "".join((t.text or "") for t in cell.findall(f".//{hp('t')}")).strip()


def element_text(elem):
    return "".join((t.text or "") for t in elem.findall(f".//{hp('t')}")).strip()


def _section_number_from_heading(text):
    normalized = re.sub(r"\s+", "", str(text or ""))
    match = re.match(r"^(0\d)[·.)-]", normalized)
    return match.group(1) if match else ""


def enforce_fixed_page_layout(block, is_first_block):
    for elem in block:
        if etree.QName(elem).localname == "p":
            elem.set("pageBreak", "0")

    if not is_first_block and block and etree.QName(block[0]).localname == "p":
        block[0].set("pageBreak", "1")

    for elem in block:
        if etree.QName(elem).localname != "p" or elem.findall(".//hp:tbl", NS):
            continue
        if _section_number_from_heading(element_text(elem)) in SENTENCE_PAGE_BREAK_SECTION_NUMBERS:
            elem.set("pageBreak", "1")


SENTENCE_NO_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮\d]+$")
TOPIC_SENTENCE_DIGIT_RE = re.compile(r"\d+")
CIRCLED_TO_DIGIT = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",
    "⑪": "11",
    "⑫": "12",
    "⑬": "13",
    "⑭": "14",
    "⑮": "15",
}


def _normalize_header_text(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def _english_signal_score(text):
    text = str(text or "")
    latin = len(re.findall(r"[A-Za-z]", text))
    slash = text.count("/")
    spaces = text.count(" ")
    return latin * 5 + slash * 2 + spaces


def _korean_signal_score(text):
    text = str(text or "")
    hangul = len(re.findall(r"[가-힣]", text))
    slash = text.count("/")
    spaces = text.count(" ")
    return hangul * 5 + slash * 2 + spaces


def _looks_like_sentence_no(text):
    return bool(SENTENCE_NO_RE.match(str(text or "").strip()))


def _normalize_topic_sentence_no(value):
    text = str(value or "").strip()
    if not text:
        return ""

    for circled, digit in CIRCLED_TO_DIGIT.items():
        text = text.replace(circled, digit)

    digit_match = TOPIC_SENTENCE_DIGIT_RE.search(text)
    if digit_match:
        return str(int(digit_match.group(0)))

    return text



def detect_sentence_table_columns(tbl):
    rows = child_rows(tbl)
    if not rows:
        return {
            "number_idx": 0,
            "english_idx": 1,
            "korean_idx": 2,
            "clear_indices": [],
            "highlight_indices": [0, 1, 2],
            "has_header": False,
        }

    has_header = _looks_like_sentence_header_row(rows[0])
    header_cells = child_cells(rows[0]) if has_header else []
    header_texts = [cell_text(cell) for cell in header_cells]
    normalized_headers = [_normalize_header_text(text) for text in header_texts]

    data_rows = rows[1:] if has_header else rows
    data_cells_by_col = defaultdict(list)
    for row in data_rows:
        for idx, cell in enumerate(child_cells(row)):
            data_cells_by_col[idx].append(cell_text(cell))

    col_indices = list(range(max(len(header_cells), max(data_cells_by_col.keys(), default=-1) + 1)))

    def pick_header(candidates):
        for idx, text in enumerate(normalized_headers):
            if any(candidate in text for candidate in candidates):
                return idx
        return None

    number_idx = pick_header(["문장", "번호"])
    if number_idx is None:
        best_idx = None
        best_score = -1
        for idx in col_indices:
            samples = data_cells_by_col.get(idx, [])
            score = sum(1 for sample in samples if _looks_like_sentence_no(sample))
            if score > best_score:
                best_score = score
                best_idx = idx
        number_idx = best_idx if best_idx is not None else 0

    english_idx = pick_header(["지문분석", "본문", "영어"])
    korean_idx = pick_header(["직독직해", "해석", "한국어"])

    remaining = [idx for idx in col_indices if idx != number_idx]

    if english_idx is None:
        english_idx = max(
            remaining,
            key=lambda idx: _english_signal_score(" ".join(data_cells_by_col.get(idx, []))),
            default=1 if len(col_indices) > 1 else 0,
        )

    remaining = [idx for idx in remaining if idx != english_idx]

    if korean_idx is None:
        korean_idx = max(
            remaining,
            key=lambda idx: _korean_signal_score(" ".join(data_cells_by_col.get(idx, []))),
            default=english_idx,
        )

    used = {number_idx, english_idx, korean_idx}
    clear_indices = []
    for idx in col_indices:
        if idx in used:
            continue
        header = normalized_headers[idx] if idx < len(normalized_headers) else ""
        samples = "".join(data_cells_by_col.get(idx, []))
        if "출제포인트" in header or not header or not samples.strip():
            clear_indices.append(idx)

    highlight_indices = [idx for idx in [number_idx, english_idx, korean_idx] if idx is not None]

    return {
        "number_idx": number_idx,
        "english_idx": english_idx,
        "korean_idx": korean_idx,
        "clear_indices": clear_indices,
        "highlight_indices": highlight_indices,
        "has_header": has_header,
    }



def _collect_run_charpr_ids(cell):
    charpr_ids = []
    for para in cell_paras(cell):
        for run in para_runs(para):
            char_pr = run.get("charPrIDRef", "")
            if char_pr:
                charpr_ids.append(char_pr)
    return charpr_ids


def _set_cell_run_charpr(cell, char_pr_id):
    if not char_pr_id:
        return
    for para in cell_paras(cell):
        for run in para_runs(para):
            run.set("charPrIDRef", str(char_pr_id))


def infer_sentence_highlight_styles(tbl, target_indices=None, number_idx=0):
    rows, _ = _table_data_rows(tbl, _looks_like_sentence_header_row)
    data_rows = rows
    if not data_rows:
        return {}, {}, "", ""

    if target_indices is not None:
        target_indices = set(target_indices)

    style_counters = defaultdict(Counter)
    number_char_counter = Counter()

    for row in data_rows:
        cells = child_cells(row)
        for idx, cell in enumerate(cells):
            if target_indices is not None and idx not in target_indices:
                continue
            style = cell.get("borderFillIDRef", "")
            if style:
                style_counters[idx][style] += 1

        if 0 <= number_idx < len(cells):
            for char_pr in _collect_run_charpr_ids(cells[number_idx]):
                number_char_counter[char_pr] += 1

    default_styles = {}
    highlight_styles = {}

    for idx, counter in style_counters.items():
        default_style, _ = counter.most_common(1)[0]
        default_styles[idx] = default_style

        alternatives = [style for style, _ in counter.most_common() if style != default_style]
        if alternatives:
            highlight_styles[idx] = alternatives[0]

    default_number_charpr = ""
    highlight_number_charpr = ""

    if number_char_counter:
        default_number_charpr, _ = number_char_counter.most_common(1)[0]
        number_alternatives = [char_pr for char_pr, _ in number_char_counter.most_common() if char_pr != default_number_charpr]
        if number_alternatives:
            highlight_number_charpr = number_alternatives[0]

    return default_styles, highlight_styles, default_number_charpr, highlight_number_charpr



def apply_topic_sentence_highlight(
    tbl,
    topic_sentence_no,
    default_styles,
    highlight_styles,
    number_idx=0,
    default_number_charpr="",
    highlight_number_charpr="",
):
    rows, _ = _table_data_rows(tbl, _looks_like_sentence_header_row)
    normalized_topic_sentence_no = _normalize_topic_sentence_no(topic_sentence_no)
    for row in rows:
        cells = child_cells(row)
        if not cells or number_idx >= len(cells):
            continue

        row_no = _normalize_topic_sentence_no(cell_text(cells[number_idx]))
        is_topic = bool(normalized_topic_sentence_no) and row_no == normalized_topic_sentence_no

        for idx, highlight_border in highlight_styles.items():
            if idx >= len(cells):
                continue

            if is_topic:
                cells[idx].set("borderFillIDRef", highlight_border)
            else:
                default_border = default_styles.get(idx)
                if default_border:
                    cells[idx].set("borderFillIDRef", default_border)

        if is_topic and highlight_number_charpr:
            _set_cell_run_charpr(cells[number_idx], highlight_number_charpr)
        elif default_number_charpr:
            _set_cell_run_charpr(cells[number_idx], default_number_charpr)


def minimize_sentence_row_height_for_auto_fit(row):
    for cell in child_cells(row):
        _, _, cell_sz, _ = ensure_cell_meta(cell)
        cell_sz.set("height", AUTO_FIT_SENTENCE_ROW_HEIGHT)
        get_sublist(cell).set("textHeight", "0")


def replace_pronunciation_content(cell, sentence):
    """Fill the original wide-cell pronunciation layout, if present."""
    templates = cell_paras(cell)
    if len(templates) < 3:
        raise ValueError("발음 템플릿의 문장 칸에 영어·발음·해석 서식이 필요합니다.")
    sub = get_sublist(cell)
    for paragraph in templates:
        sub.remove(paragraph)
    for template, key in zip(templates[:3], ("영어", "한글발음", "한국어")):
        # Explicit newlines get their own paragraphs; no slash or spacing is changed.
        for line in sentence[key].split("\n"):
            sub.append(make_para_like(template, line))


def replace_pronunciation_in_english_cell(english_cell, korean_cell, sentence):
    """Keep the user's English / purple pronunciation / blank paragraph design."""
    templates = cell_paras(english_cell)
    if len(templates) < 2:
        raise ValueError("발음 템플릿 영어 칸에 영어·발음 문단이 필요합니다.")
    sub = get_sublist(english_cell)
    for paragraph in templates:
        sub.remove(paragraph)
    for template, key in ((templates[0], "영어"), (templates[1], "한글발음")):
        for line in sentence[key].split("\n"):
            sub.append(make_para_like(template, line))
    if len(templates) >= 3:
        sub.append(make_para_like(templates[2], ""))

    korean_template = cell_paras(korean_cell)
    if not korean_template:
        raise ValueError("발음 템플릿 직독직해 칸에 문단 서식이 필요합니다.")
    korean_sub = get_sublist(korean_cell)
    for paragraph in korean_template:
        korean_sub.remove(paragraph)
    for line in sentence["한국어"].split("\n"):
        korean_sub.append(make_para_like(korean_template[0], line))
    if len(korean_template) >= 2:
        korean_sub.append(make_para_like(korean_template[1], ""))


def patch_sentences(tbl, c, pronunciation=False):
    sents = c.get("지문", [])
    rows = child_rows(tbl)
    if not rows or not sents:
        return

    if pronunciation:
        sample_cell_count = len(child_cells(rows[0]))
        if sample_cell_count not in (3, 5):
            raise ValueError("발음용 03 지문 분석 표는 3셀 또는 5셀 문장 행이어야 합니다.")
        col_map = {
            "has_header": False, "number_idx": 0, "english_idx": 2,
            "korean_idx": 4 if sample_cell_count == 5 else 2,
            "clear_indices": [1, 3] if sample_cell_count == 5 else [],
            "highlight_indices": [0, 2, 4] if sample_cell_count == 5 else [0, 2],
        }
    else:
        col_map = detect_sentence_table_columns(tbl)
    has_header = col_map.get("has_header", False)
    dr = rows[1:] if has_header else rows
    if not dr:
        return

    # Capture the template's alternate highlight style before rows are
    # duplicated or trimmed; otherwise short passages can delete the only
    # highlighted sample row and lose the style information entirely.
    default_styles, highlight_styles, default_number_charpr, highlight_number_charpr = infer_sentence_highlight_styles(
        tbl,
        target_indices=col_map.get("highlight_indices"),
        number_idx=col_map.get("number_idx", 0),
    )

    while len(dr) < len(sents):
        tbl.append(copy.deepcopy(dr[-1]))
        dr = child_rows(tbl)[1:] if has_header else child_rows(tbl)
    while len(dr) > len(sents):
        tbl.remove(dr[-1])
        dr = child_rows(tbl)[1:] if has_header else child_rows(tbl)

    target_rows = child_rows(tbl)[1:] if has_header else child_rows(tbl)
    for row, sent in zip(target_rows, sents):
        # 기존 샘플 행의 큰 높이를 물려받지 않도록 텍스트를 넣기 전에 최소화한다.
        minimize_sentence_row_height_for_auto_fit(row)
        cells = child_cells(row)
        if not cells:
            continue

        number_idx = col_map.get("number_idx", 0)
        english_idx = col_map.get("english_idx", 1)
        korean_idx = col_map.get("korean_idx", 2)

        if number_idx < len(cells):
            replace_cell_text(cells[number_idx], sent.get("번호", ""))
        if pronunciation:
            if len(cells) == 5:
                replace_pronunciation_in_english_cell(cells[2], cells[4], sent)
            elif len(cells) == 3 and cells[2].find(f"./{hp('cellSpan')}").get("colSpan") == "3":
                replace_pronunciation_content(cells[2], sent)
            else:
                raise ValueError("선택한 HWPX는 발음용 03 템플릿이 아닙니다.")
        elif english_idx < len(cells):
            replace_cell_text_with_trailing_blank_line(cells[english_idx], sent.get("영어", ""))
        if not pronunciation and korean_idx < len(cells):
            replace_cell_text_with_trailing_blank_line(cells[korean_idx], sent.get("한국어", ""))

        for clear_idx in col_map.get("clear_indices", []):
            if clear_idx < len(cells):
                replace_cell_text(cells[clear_idx], "")

    apply_topic_sentence_highlight(
        tbl,
        c.get("주제문_번호", ""),
        default_styles,
        highlight_styles,
        number_idx=col_map.get("number_idx", 0),
        default_number_charpr=default_number_charpr,
        highlight_number_charpr=highlight_number_charpr,
    )


def _clear_vocab_row(row):
    cells = child_cells(row)
    for idx in range(min(5, len(cells))):
        replace_cell_text(cells[idx], "")


def patch_vocab(tbl, c):
    words = c.get("어휘", [])
    rows = child_rows(tbl)
    if not rows:
        return

    dr = rows[1:]
    if not words:
        # 어휘가 비어 있을 때 템플릿 샘플 문구가 남지 않도록 데이터 행을 비운다.
        if not dr:
            return
        while len(dr) > 1:
            tbl.remove(dr[-1])
            dr = child_rows(tbl)[1:]
        _clear_vocab_row(dr[0])
        return

    while len(dr) < len(words):
        tbl.append(copy.deepcopy(dr[-1]))
        dr = child_rows(tbl)[1:]
    while len(dr) > len(words):
        tbl.remove(dr[-1])
        dr = child_rows(tbl)[1:]

    for row, word in zip(child_rows(tbl)[1:], words):
        cells = child_cells(row)
        if len(cells) >= 5:
            replace_cell_text(cells[0], word.get("단어", ""))
            replace_cell_text(cells[1], word.get("뜻", ""))
            replace_cell_text(cells[2], word.get("동의어", ""))
            replace_cell_text(cells[3], word.get("반의어", ""))
            replace_cell_text(cells[4], word.get("반의어_뜻", ""))


def patch_all(tables, content, pronunciation=False):
    if len(tables) > 0:
        patch_header(tables[0], content)
    if len(tables) > 1:
        patch_summary(tables[1], content)
    if len(tables) > 2:
        patch_background(tables[2], content)
    if len(tables) > 3:
        patch_analysis(tables[3], content)
    if len(tables) > 4:
        patch_sentences(tables[4], content, pronunciation=pronunciation)
    if len(tables) > 5:
        patch_vocab(tables[5], content)



def _require_type(value, expected_type, field_name):
    if not isinstance(value, expected_type):
        expected = expected_type.__name__
        actual = type(value).__name__
        raise TypeError(f"{field_name}의 자료형이 잘못되었습니다. expected={expected}, actual={actual}")


def _validate_string_field(obj, key, field_name):
    if key not in obj:
        raise KeyError(f"{field_name} 키가 없습니다.")
    _require_type(obj[key], str, field_name)


def _validate_list_of_strings(obj, key, field_name):
    if key not in obj:
        raise KeyError(f"{field_name} 키가 없습니다.")
    _require_type(obj[key], list, field_name)
    for idx, item in enumerate(obj[key]):
        _require_type(item, str, f"{field_name}[{idx}]")


def _validate_background_list(obj, key, field_name):
    if key not in obj:
        raise KeyError(f"{field_name} 키가 없습니다.")
    _require_type(obj[key], list, field_name)
    for idx, item in enumerate(obj[key]):
        _require_type(item, dict, f"{field_name}[{idx}]")
        _validate_string_field(item, "제목", f"{field_name}[{idx}].제목")
        _validate_string_field(item, "내용", f"{field_name}[{idx}].내용")


def _validate_sentence_list(obj, key, field_name, pronunciation=False, passage_number=""):
    if key not in obj:
        raise KeyError(f"{field_name} 키가 없습니다.")
    _require_type(obj[key], list, field_name)
    if not obj[key]:
        raise ValueError(f"지문 {passage_number}: 문장 배열이 비어 있습니다.")
    for idx, item in enumerate(obj[key]):
        _require_type(item, dict, f"{field_name}[{idx}]")
        _validate_string_field(item, "번호", f"{field_name}[{idx}].번호")
        _validate_string_field(item, "영어", f"{field_name}[{idx}].영어")
        _validate_string_field(item, "한국어", f"{field_name}[{idx}].한국어")
        if pronunciation:
            location = f"지문 {passage_number} · 문장 {item['번호']}"
            if "한글발음" not in item:
                raise ValueError(f"{location}: 한글발음이 누락되었습니다.")
            if not isinstance(item["한글발음"], str):
                raise ValueError(f"{location}: 한글발음은 문자열이어야 합니다.")
            if not item["한글발음"].strip():
                raise ValueError(f"{location}: 한글발음이 비어 있습니다.")


def _validate_vocab_list(obj, key, field_name):
    if key not in obj:
        raise KeyError(f"{field_name} 키가 없습니다.")
    _require_type(obj[key], list, field_name)
    for idx, item in enumerate(obj[key]):
        _require_type(item, dict, f"{field_name}[{idx}]")
        _validate_string_field(item, "단어", f"{field_name}[{idx}].단어")
        _validate_string_field(item, "뜻", f"{field_name}[{idx}].뜻")
        _validate_string_field(item, "동의어", f"{field_name}[{idx}].동의어")
        _validate_string_field(item, "반의어", f"{field_name}[{idx}].반의어")
        _validate_string_field(item, "반의어_뜻", f"{field_name}[{idx}].반의어_뜻")


def validate_input(data, pronunciation=False, output_mode="compatibility"):
    if output_mode not in ("compatibility", "v2"):
        raise ValueError("출력 모드는 'compatibility' 또는 'v2'여야 합니다.")
    if "PASSAGES" not in data:
        raise KeyError('최상위 키 "PASSAGES"가 없습니다.')
    _require_type(data["PASSAGES"], list, "PASSAGES")
    if not data["PASSAGES"]:
        raise ValueError("input.json의 PASSAGES 배열이 비어 있습니다.")

    for p_idx, passage in enumerate(data["PASSAGES"]):
        field_name = f"PASSAGES[{p_idx}]"
        _require_type(passage, dict, field_name)

        missing = [key for key in PASSAGE_REQUIRED_KEYS if key not in passage]
        if missing:
            raise KeyError(f"{field_name}에 필수 키가 누락되었습니다: {', '.join(missing)}")

        for key in SCALAR_STRING_KEYS:
            _validate_string_field(passage, key, f"{field_name}.{key}")

        _validate_background_list(passage, "배경_지식", f"{field_name}.배경_지식")
        _validate_list_of_strings(passage, "소재", f"{field_name}.소재")
        _validate_sentence_list(passage, "지문", f"{field_name}.지문", pronunciation, passage["번호"])
        _validate_vocab_list(passage, "어휘", f"{field_name}.어휘")
        if output_mode == "v2":
            validate_logic_visualization(passage, p_idx)


def get_output_path(passages, workdir: Path) -> Path:
    nums = "_".join(str(p["번호"]) for p in passages)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    return workdir / f"분석결과_{nums}_{timestamp}.hwpx"


def find_child_index_with_table(root, table_idx):
    all_tables = root.findall('.//hp:tbl', NS)
    top_children = list(root)
    for i, ch in enumerate(top_children):
        tbls = ch.findall('.//hp:tbl', NS)
        if tbls and all_tables.index(tbls[0]) == table_idx:
            return i
    return -1


def ensure_cell_meta(cell):
    cell_addr = ensure_child(cell, "cellAddr")
    cell_span = ensure_child(cell, "cellSpan")
    cell_sz = ensure_child(cell, "cellSz")
    cell_margin = ensure_child(cell, "cellMargin")

    if "colSpan" not in cell_span.attrib:
        cell_span.set("colSpan", "1")
    if "rowSpan" not in cell_span.attrib:
        cell_span.set("rowSpan", "1")
    if "width" not in cell_sz.attrib:
        cell_sz.set("width", "0")
    if "height" not in cell_sz.attrib:
        cell_sz.set("height", "0")
    for key in ("left", "right", "top", "bottom"):
        if key not in cell_margin.attrib:
            cell_margin.set(key, "0")

    return cell_addr, cell_span, cell_sz, cell_margin


def max_row_height(row):
    heights = []
    for cell in child_cells(row):
        cell_sz = cell.find(f"./{hp('cellSz')}")
        if cell_sz is not None:
            height = _safe_int(cell_sz.get("height"), 0)
            cell_span = cell.find(f"./{hp('cellSpan')}")
            row_span = max(1, _safe_int(cell_span.get("rowSpan"), 1) if cell_span is not None else 1)
            if row_span > 1:
                height = max(1, (height + row_span - 1) // row_span)
            heights.append(height)
    return max(heights) if heights else 0


def normalize_table_structure(tbl):
    rows = child_rows(tbl)
    tbl.set("rowCnt", str(len(rows)))

    total_height = 0
    max_cols = 0

    # 병합 셀이 있는 표의 cellAddr를 정규화할 때 rowSpan 점유 정보를 유지한다.
    occupied_until = {}

    for row_idx, row in enumerate(rows):
        logical_col = 0

        def advance_past_rowspans(col_idx):
            while occupied_until.get(col_idx, -1) >= row_idx:
                col_idx += 1
            return col_idx

        logical_col = advance_past_rowspans(logical_col)

        for cell in child_cells(row):
            logical_col = advance_past_rowspans(logical_col)

            cell_addr, cell_span, _, _ = ensure_cell_meta(cell)
            col_span = int(cell_span.get("colSpan", "1") or "1")
            row_span = int(cell_span.get("rowSpan", "1") or "1")

            if col_span < 1:
                col_span = 1
                cell_span.set("colSpan", "1")
            if row_span < 1:
                row_span = 1
                cell_span.set("rowSpan", "1")

            cell_addr.set("colAddr", str(logical_col))
            cell_addr.set("rowAddr", str(row_idx))

            if row_span > 1:
                for offset in range(col_span):
                    occupied_until[logical_col + offset] = row_idx + row_span - 1

            logical_col += col_span
            logical_col = advance_past_rowspans(logical_col)

        visible_cols = logical_col
        while occupied_until.get(visible_cols, -1) >= row_idx:
            visible_cols += 1

        max_cols = max(max_cols, visible_cols)
        total_height += max_row_height(row)

    if max_cols > 0:
        tbl.set("colCnt", str(max_cols))

    tbl_sz = tbl.find(f"./{hp('sz')}")
    if tbl_sz is not None and total_height > 0:
        tbl_sz.set("height", str(total_height))


def normalize_all_tables(root):
    for tbl in root.findall('.//hp:tbl', NS):
        normalize_table_structure(tbl)


def unlock_document_editing(section_root, header_root=None):
    for elem in section_root.iter():
        if "editable" in elem.attrib:
            elem.set("editable", "1")
        if "protect" in elem.attrib:
            elem.set("protect", "0")
        if "lock" in elem.attrib:
            elem.set("lock", "0")

    if header_root is None:
        return

    # Some templates carry change-tracking metadata that can make the output
    # feel protected/read-only in Hancom Office. Remove it for generated files.
    for track_config in header_root.findall(".//hh:trackchageConfig", NS):
        parent = track_config.getparent()
        if parent is not None:
            parent.remove(track_config)



def count_tables_in_elements(elements):
    count = 0
    for elem in elements:
        count += len(elem.findall('.//hp:tbl', NS))
    return count


def load_range_map(path, passage_count):
    if not path:
        return None
    range_map_path = Path(path)
    if not range_map_path.is_file():
        raise FileNotFoundError(f"지문별 범위 파일을 찾지 못했습니다: {range_map_path}")
    with range_map_path.open("r", encoding="utf-8") as file:
        range_map = json.load(file)
    if not isinstance(range_map, list) or len(range_map) != passage_count:
        raise ValueError(f"지문별 범위는 지문 수와 같은 배열이어야 합니다: {passage_count}개")
    for index, value in enumerate(range_map, start=1):
        if not isinstance(value, str):
            raise ValueError(f"지문 {index}의 범위는 문자열이어야 합니다.")
        if "\n" in value or "\r" in value or len(value) > 40:
            raise ValueError(f"지문 {index}의 범위는 줄바꿈 없이 40자 이하여야 합니다.")
    return range_map



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pronunciation", choices=("included", "excluded"), default="excluded")
    parser.add_argument("--mode", choices=("compatibility", "v2"), default="compatibility")
    parser.add_argument("--template", help="작업 폴더에 있는 HWPX 템플릿 파일명")
    parser.add_argument("--school", default="", help="각 페이지 머리말 왼쪽 위에 표시할 학교")
    parser.add_argument("--range-text", default="", help="각 페이지 머리말 오른쪽 위에 표시할 범위")
    parser.add_argument("--range-map-file", default="", help="지문 순서별 오른쪽 머리말 문자열 배열 JSON")
    args = parser.parse_args()
    expected_name = ("analysis_template_pronunciation.hwpx" if args.pronunciation == "included"
                     else "analysis_template.hwpx")
    template_name = args.template or expected_name
    if Path(template_name).name != expected_name:
        raise ValueError("선택한 발음 옵션과 HWPX 템플릿이 일치하지 않습니다.")
    workdir = Path.cwd()
    input_json = workdir / "input.json"

    if not input_json.exists():
        raise FileNotFoundError("현재 폴더에 input.json 파일이 없습니다.")

    with input_json.open("r", encoding="utf-8") as f:
        data = json.load(f)

    validate_input(
        data,
        pronunciation=args.pronunciation == "included",
        output_mode=args.mode,
    )
    passages = data["PASSAGES"]
    range_map = load_range_map(args.range_map_file, len(passages))
    if range_map is None:
        range_map = [args.range_text] * len(passages)
    template_path = workdir / template_name
    if not template_path.is_file():
        raise FileNotFoundError(f"HWPX 템플릿을 찾지 못했습니다: {template_path}")

    work_xml_dir = workdir / "_hwpx_build_tmp"
    if work_xml_dir.exists():
        shutil.rmtree(work_xml_dir)
    work_xml_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(template_path, "r") as zf:
        zf.extractall(work_xml_dir)

    header_xml = work_xml_dir / "Contents" / "header.xml"
    section_xml = work_xml_dir / "Contents" / "section0.xml"
    if not section_xml.exists():
        raise FileNotFoundError("HWPX 템플릿 안에 Contents/section0.xml 이 없습니다.")

    tree = etree.parse(str(section_xml))
    root = tree.getroot()
    header_tree = etree.parse(str(header_xml)) if header_xml.exists() else None
    header_root = header_tree.getroot() if header_tree is not None else None

    top_children = list(root)
    # 템플릿의 6개 표는 그대로 유지하고 V2 모드에서만 05 제목·그림을 사용한다.
    template_block = [copy.deepcopy(e) for e in top_children]
    if args.mode == "compatibility":
        template_block = remove_logic_elements(template_block)
    tables_per_block = count_tables_in_elements(template_block)
    if tables_per_block != 6:
        raise ValueError(f"00~04 템플릿 표는 6개여야 합니다. actual={tables_per_block}")

    for elem in list(root):
        root.remove(elem)

    for idx, content in enumerate(passages):
        block = [copy.deepcopy(e) for e in template_block]
        patch_page_header(block, args.school, range_map[idx])
        if args.mode == "v2":
            diagrams_dir = workdir / "diagrams"
            diagram_path = diagrams_dir / f"logic_{idx + 1:03d}.png"
            render_logic_visualization(content, diagram_path)
            resource_id = f"logic_{idx + 1:03d}"
            replace_logic_picture(block, resource_id, idx)
            add_png_resource(work_xml_dir, resource_id, diagram_path)
        enforce_fixed_page_layout(block, is_first_block=(idx == 0))
        for elem in block:
            root.append(elem)

        block_tables = root.findall('.//hp:tbl', NS)[idx * tables_per_block:(idx + 1) * tables_per_block]
        patch_all(block_tables, content, pronunciation=args.pronunciation == "included")

    remove_placeholder_resource(work_xml_dir)
    normalize_all_tables(root)
    unlock_document_editing(root, header_root)
    tree.write(str(section_xml), xml_declaration=True, encoding="UTF-8", standalone=True)
    if header_tree is not None:
        header_tree.write(str(header_xml), xml_declaration=True, encoding="UTF-8", standalone=True)

    output_path = get_output_path(passages, workdir)
    # HWPX 규격: mimetype은 반드시 STORED(비압축)로 첫 번째에 저장해야 함
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) mimetype 먼저, STORED로
        mimetype_path = work_xml_dir / "mimetype"
        if mimetype_path.exists():
            zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
        # 2) 나머지 파일들 DEFLATED로
        for dirpath, _, filenames in os.walk(work_xml_dir):
            for fname in filenames:
                fpath = Path(dirpath) / fname
                arcname = fpath.relative_to(work_xml_dir)
                if str(arcname) == "mimetype":
                    continue
                zf.write(fpath, arcname)

    image_report = validate_hwpx_image_references(output_path)
    if not image_report["ok"]:
        output_path.unlink(missing_ok=True)
        raise ValueError("HWPX 이미지 참조 검증 실패: " + "; ".join(image_report["errors"]))
    if args.mode == "v2" and len(image_report["logic_image_references"]) != len(passages):
        output_path.unlink(missing_ok=True)
        raise ValueError("HWPX 논리 시각화 이미지 수가 지문 수와 일치하지 않습니다.")

    shutil.rmtree(work_xml_dir)
    print(f"완료: {output_path.name}")


if __name__ == "__main__":
    main()
