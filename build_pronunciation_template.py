#!/usr/bin/env python3
"""Copy the current base HWPX, adding only a pronunciation line to section 03."""

import argparse
import copy
import zipfile
from pathlib import Path

from lxml import etree


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "analysis_template.hwpx"
TARGET = ROOT / "analysis_template_pronunciation.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS = {"hp": HP, "hh": HH}


def add_pronunciation_styles(header):
    char_list = header.find(".//hh:charProperties", NS)
    para_list = header.find(".//hh:paraProperties", NS)
    if char_list is None or para_list is None:
        raise ValueError("HWPX 문자·문단 서식 목록을 찾지 못했습니다.")

    base_char = header.find(f".//{{{HH}}}charPr[@id='3']")
    base_para = header.find(f".//{{{HH}}}paraPr[@id='0']")
    if base_char is None or base_para is None:
        raise ValueError("영어 지문 기준 서식을 찾지 못했습니다.")

    char_id = max(int(style.get("id")) for style in char_list.findall(f"./{{{HH}}}charPr")) + 1
    para_id = max(int(style.get("id")) for style in para_list.findall(f"./{{{HH}}}paraPr")) + 1
    pron_char = copy.deepcopy(base_char)
    pron_char.set("id", str(char_id))
    pron_char.set("height", "800")
    pron_char.set("textColor", "#9D5CBB")
    char_list.append(pron_char)
    char_list.set("itemCnt", str(len(char_list.findall(f"./{{{HH}}}charPr"))))

    pron_para = copy.deepcopy(base_para)
    pron_para.set("id", str(para_id))
    for spacing in pron_para.findall(f".//{{{HH}}}lineSpacing"):
        spacing.set("value", "150")
    para_list.append(pron_para)
    para_list.set("itemCnt", str(len(para_list.findall(f"./{{{HH}}}paraPr"))))
    return char_id, para_id


def make_pronunciation_paragraph(english_paragraph, char_id, para_id):
    paragraph = copy.deepcopy(english_paragraph)
    paragraph.set("paraPrIDRef", str(para_id))
    for segment in paragraph.findall(f"./{{{HP}}}linesegarray"):
        paragraph.remove(segment)
    runs = paragraph.findall(f"./{{{HP}}}run")
    if not runs:
        raise ValueError("03 영어 칸에 문장 서식이 없습니다.")
    for extra in runs[1:]:
        paragraph.remove(extra)
    run = runs[0]
    run.set("charPrIDRef", str(char_id))
    for child in list(run):
        run.remove(child)
    etree.SubElement(run, f"{{{HP}}}t").text = "한글 발음"
    return paragraph


def run(output=TARGET):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"기존 파일을 덮어쓰지 않습니다: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"출력 폴더가 없습니다: {output.parent}")
    with zipfile.ZipFile(SOURCE) as source:
        section = etree.fromstring(source.read("Contents/section0.xml"))
        header = etree.fromstring(source.read("Contents/header.xml"))
        char_id, para_id = add_pronunciation_styles(header)

        tables = section.findall(".//hp:tbl", NS)
        if len(tables) != 6:
            raise ValueError(f"예상한 00~04 템플릿 표 6개가 아닙니다: {len(tables)}")
        table = tables[4]
        rows = table.findall(f"./{{{HP}}}tr")
        for row in rows:
            cells = row.findall(f"./{{{HP}}}tc")
            if len(cells) != 5:
                raise ValueError("03 지문 분석 표는 5열이어야 합니다.")
            english = cells[2]
            sub = english.find(f"./{{{HP}}}subList")
            paragraphs = sub.findall(f"./{{{HP}}}p") if sub is not None else []
            if len(paragraphs) < 2:
                raise ValueError("03 영어 칸에 영어 문단과 기존 빈 문단이 필요합니다.")
            position = list(sub).index(paragraphs[0]) + 1
            sub.insert(position, make_pronunciation_paragraph(paragraphs[0], char_id, para_id))

        replacements = {
            "Contents/section0.xml": etree.tostring(section, xml_declaration=True, encoding="UTF-8", standalone=True),
            "Contents/header.xml": etree.tostring(header, xml_declaration=True, encoding="UTF-8", standalone=True),
        }
        with zipfile.ZipFile(output, "x") as destination:
            for member in source.infolist():
                destination.writestr(member, replacements.get(member.filename, source.read(member)))
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=TARGET)
    run(parser.parse_args().output)
