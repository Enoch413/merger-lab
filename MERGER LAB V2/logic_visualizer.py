#!/usr/bin/env python3
"""Validate approved V2 logic data and render a print-ready PNG diagram."""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCHEMA_VERSION = "1.0.0"
DIAGRAM_TYPES = {
    "CAUSAL_FLOW",
    "CONTRAST",
    "ANALOGY",
    "PROCESS",
    "PROBLEM_SOLUTION",
    "CLAIM_EVIDENCE",
    "GENERAL_TO_SPECIFIC",
    "MIXED",
}
RELATIONS = {
    "CAUSE",
    "CONTRAST",
    "ANALOGY",
    "SEQUENCE",
    "PROBLEM_SOLUTION",
    "EVIDENCE",
    "EXAMPLE",
    "ELABORATION",
}
LAYOUTS = {"FLOW", "CONTRAST_COLUMNS", "ANALOGY_MAP", "BRANCH"}
TARGET = "A4_HALF_PAGE"

LOGIC_KEYS = {
    "schema_version", "diagram_type", "selection_reason", "nodes", "edges",
    "analogies", "rendering",
}
NODE_KEYS = {"id", "sentence_numbers", "role", "label", "evidence"}
EDGE_KEYS = {"id", "from", "to", "relation", "label", "evidence"}
EVIDENCE_KEYS = {"sentence_no", "quote"}
RENDERING_KEYS = {"layout", "reading_order", "groups", "target", "show_title"}
GROUP_KEYS = {"id", "label", "node_ids"}
ANALOGY_KEYS = {
    "id", "node_id", "vehicle", "target", "core_property", "limit",
    "mappings", "evidence",
}
MAPPING_KEYS = {"vehicle_property", "target_property", "evidence"}

NODE_ID_RE = re.compile(r"^N[1-9][0-9]*$")
EDGE_ID_RE = re.compile(r"^E[1-9][0-9]*$")
ANALOGY_ID_RE = re.compile(r"^A[1-9][0-9]*$")
GROUP_ID_RE = re.compile(r"^G[1-9][0-9]*$")
SENTENCE_NO_RE = re.compile(r"^[1-9][0-9]*$")

CANVAS_SIZE = (1800, 1060)
FONT_REGULAR = Path(r"C:\Windows\Fonts\malgun.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\malgunbd.ttf")

COLORS = {
    "background": "#FBF8F1",
    "node_fill": "#F3F7F2",
    "node_fill_alt": "#FFF9EE",
    "node_border": "#426B5C",
    "role": "#23594B",
    "ink": "#202925",
    "muted": "#5E675F",
    "edge": "#3C5149",
    "cause": "#745043",
    "contrast": "#385E70",
    "label_fill": "#FFFDF8",
    "label_border": "#B9B3A6",
    "badge_fill": "#DDEADF",
    "badge_ink": "#234A3F",
}

RELATION_KO = {
    "CAUSE": "인과",
    "CONTRAST": "대조",
    "ANALOGY": "비유",
    "SEQUENCE": "순서",
    "PROBLEM_SOLUTION": "문제·해결",
    "EVIDENCE": "근거",
    "EXAMPLE": "예시",
    "ELABORATION": "부연",
}


class LogicValidationError(ValueError):
    """Raised when approved logic data violates the V2 rendering contract."""


def _fail(location: str, message: str):
    raise LogicValidationError(f"{location}: {message}")


def _require_object(value, location: str):
    if not isinstance(value, dict):
        _fail(location, "객체여야 합니다.")
    return value


def _require_array(value, location: str, minimum=None, maximum=None):
    if not isinstance(value, list):
        _fail(location, "배열이어야 합니다.")
    if minimum is not None and len(value) < minimum:
        _fail(location, f"항목이 최소 {minimum}개 필요합니다.")
    if maximum is not None and len(value) > maximum:
        _fail(location, f"항목은 최대 {maximum}개까지 허용됩니다.")
    return value


def _require_string(value, location: str, maximum=None, pattern=None):
    if not isinstance(value, str):
        _fail(location, "문자열이어야 합니다.")
    if not value.strip():
        _fail(location, "빈 문자열일 수 없습니다.")
    if maximum is not None and len(value) > maximum:
        _fail(location, f"길이는 최대 {maximum}자여야 합니다.")
    if pattern is not None and not pattern.fullmatch(value):
        _fail(location, "허용된 형식이 아닙니다.")
    return value


def _require_exact_keys(value: dict, expected: set[str], location: str):
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing:
        _fail(location, f"필수 키가 없습니다: {', '.join(missing)}")
    if extra:
        _fail(location, f"허용되지 않은 키가 있습니다: {', '.join(extra)}")


def _require_unique(values, location: str):
    if len(values) != len(set(values)):
        _fail(location, "중복 값이 있습니다.")


def _normalized_evidence(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    text = re.sub(r"\s*/\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _validate_evidence(items, sentence_map, location: str):
    _require_array(items, location, minimum=1)
    for index, item in enumerate(items):
        item_location = f"{location}[{index}]"
        _require_object(item, item_location)
        _require_exact_keys(item, EVIDENCE_KEYS, item_location)
        sentence_no = _require_string(item["sentence_no"], f"{item_location}.sentence_no", pattern=SENTENCE_NO_RE)
        quote = _require_string(item["quote"], f"{item_location}.quote", maximum=160)
        if sentence_no not in sentence_map:
            _fail(item_location, f"원문에 없는 문장 번호를 참조합니다: {sentence_no}")
        if _normalized_evidence(quote) not in _normalized_evidence(sentence_map[sentence_no]):
            _fail(item_location, f"인용문이 원문 {sentence_no}번 영어 문장에 없습니다: {quote}")


def _validate_analogy(item, index, node_ids, sentence_map, location):
    item_location = f"{location}.analogies[{index}]"
    _require_object(item, item_location)
    _require_exact_keys(item, ANALOGY_KEYS, item_location)
    _require_string(item["id"], f"{item_location}.id", pattern=ANALOGY_ID_RE)
    node_id = _require_string(item["node_id"], f"{item_location}.node_id", pattern=NODE_ID_RE)
    if node_id not in node_ids:
        _fail(f"{item_location}.node_id", f"존재하지 않는 node를 참조합니다: {node_id}")
    _require_string(item["vehicle"], f"{item_location}.vehicle", maximum=40)
    _require_string(item["target"], f"{item_location}.target", maximum=40)
    _require_string(item["core_property"], f"{item_location}.core_property", maximum=60)
    _require_string(item["limit"], f"{item_location}.limit")
    mappings = _require_array(item["mappings"], f"{item_location}.mappings", 1, 3)
    for mapping_index, mapping in enumerate(mappings):
        mapping_location = f"{item_location}.mappings[{mapping_index}]"
        _require_object(mapping, mapping_location)
        _require_exact_keys(mapping, MAPPING_KEYS, mapping_location)
        _require_string(mapping["vehicle_property"], f"{mapping_location}.vehicle_property", maximum=40)
        _require_string(mapping["target_property"], f"{mapping_location}.target_property", maximum=40)
        _validate_evidence(mapping["evidence"], sentence_map, f"{mapping_location}.evidence")
    _validate_evidence(item["evidence"], sentence_map, f"{item_location}.evidence")


def _validate_graph_shape(logic, node_ids, location: str):
    edges = logic["edges"]
    adjacency = {node_id: [] for node_id in node_ids}
    neighbors = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source, target = edge["from"], edge["to"]
        if source == target:
            _fail(f"{location}.edges", f"자기 자신을 가리키는 Edge는 허용되지 않습니다: {edge['id']}")
        adjacency[source].append(target)
        neighbors[source].add(target)
        neighbors[target].add(source)

    visiting, visited = set(), set()

    def visit(node_id):
        if node_id in visiting:
            _fail(f"{location}.edges", "순환 그래프는 지원하지 않습니다.")
        if node_id in visited:
            return
        visiting.add(node_id)
        for next_id in adjacency[node_id]:
            visit(next_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in node_ids:
        visit(node_id)

    order = logic["rendering"]["reading_order"]
    layout = logic["rendering"]["layout"]
    expected_pairs = {frozenset(pair) for pair in zip(order, order[1:])}
    actual_pairs = {frozenset((edge["from"], edge["to"])) for edge in edges}
    if layout == "FLOW":
        if any(len(connected) > 2 for connected in neighbors.values()):
            _fail(f"{location}.rendering.layout", "FLOW인데 실제 그래프가 분기형입니다.")
        if actual_pairs != expected_pairs:
            _fail(f"{location}.rendering.layout", "FLOW의 Edge가 reading_order의 연속 흐름과 일치하지 않습니다.")
    elif layout == "BRANCH":
        if actual_pairs == expected_pairs:
            _fail(f"{location}.rendering.layout", "BRANCH인데 실제 그래프에 분기 Edge가 없습니다.")


def validate_logic_visualization(passage: dict, passage_index=0) -> dict:
    """Validate one passage against the V2 schema plus mechanical graph checks."""
    passage_number = passage.get("번호", passage_index + 1) if isinstance(passage, dict) else passage_index + 1
    location = f"지문 {passage_number} · 논리_시각화"
    _require_object(passage, f"지문 {passage_number}")
    if "논리_시각화" not in passage:
        _fail(location, "V2 모드에 필요한 데이터가 누락되었습니다.")
    logic = _require_object(passage["논리_시각화"], location)
    _require_exact_keys(logic, LOGIC_KEYS, location)

    if logic["schema_version"] != SCHEMA_VERSION:
        _fail(f"{location}.schema_version", f"지원 버전은 {SCHEMA_VERSION}입니다.")
    if logic["diagram_type"] not in DIAGRAM_TYPES:
        _fail(f"{location}.diagram_type", f"허용되지 않은 값입니다: {logic['diagram_type']}")
    _require_string(logic["selection_reason"], f"{location}.selection_reason")

    sentences = passage.get("지문")
    _require_array(sentences, f"지문 {passage_number} · 지문", minimum=1)
    sentence_map = {}
    for index, sentence in enumerate(sentences):
        sentence_location = f"지문 {passage_number} · 지문[{index}]"
        _require_object(sentence, sentence_location)
        number = _require_string(sentence.get("번호"), f"{sentence_location}.번호")
        english = _require_string(sentence.get("영어"), f"{sentence_location}.영어")
        if number in sentence_map:
            _fail(sentence_location, f"문장 번호가 중복되었습니다: {number}")
        sentence_map[number] = english

    nodes = _require_array(logic["nodes"], f"{location}.nodes", 3, 5)
    node_ids = []
    for index, node in enumerate(nodes):
        node_location = f"{location}.nodes[{index}]"
        _require_object(node, node_location)
        _require_exact_keys(node, NODE_KEYS, node_location)
        node_id = _require_string(node["id"], f"{node_location}.id", pattern=NODE_ID_RE)
        node_ids.append(node_id)
        numbers = _require_array(node["sentence_numbers"], f"{node_location}.sentence_numbers", minimum=1)
        for number_index, number in enumerate(numbers):
            _require_string(number, f"{node_location}.sentence_numbers[{number_index}]", pattern=SENTENCE_NO_RE)
            if number not in sentence_map:
                _fail(f"{node_location}.sentence_numbers[{number_index}]", f"원문에 없는 문장 번호입니다: {number}")
        _require_unique(numbers, f"{node_location}.sentence_numbers")
        _require_string(node["role"], f"{node_location}.role", maximum=24)
        _require_string(node["label"], f"{node_location}.label", maximum=40)
        _validate_evidence(node["evidence"], sentence_map, f"{node_location}.evidence")
    _require_unique(node_ids, f"{location}.nodes.id")
    node_id_set = set(node_ids)

    edges = _require_array(logic["edges"], f"{location}.edges", 2, 8)
    edge_ids = []
    for index, edge in enumerate(edges):
        edge_location = f"{location}.edges[{index}]"
        _require_object(edge, edge_location)
        _require_exact_keys(edge, EDGE_KEYS, edge_location)
        edge_id = _require_string(edge["id"], f"{edge_location}.id", pattern=EDGE_ID_RE)
        edge_ids.append(edge_id)
        for key in ("from", "to"):
            node_id = _require_string(edge[key], f"{edge_location}.{key}", pattern=NODE_ID_RE)
            if node_id not in node_id_set:
                _fail(f"{edge_location}.{key}", f"존재하지 않는 node를 참조합니다: {node_id}")
        relation = edge["relation"]
        if relation not in RELATIONS:
            _fail(f"{edge_location}.relation", f"허용되지 않은 값입니다: {relation}")
        label = _require_string(edge["label"], f"{edge_location}.label", maximum=24)
        _validate_evidence(edge["evidence"], sentence_map, f"{edge_location}.evidence")
        if relation == "CAUSE" and any(" may " in f" {_normalized_evidence(ev['quote'])} " for ev in edge["evidence"]):
            if not any(marker in label.casefold() for marker in ("수 있", "가능", "may")):
                _fail(f"{edge_location}.label", "원문의 may에 해당하는 가능성 표현이 보존되지 않았습니다.")
    _require_unique(edge_ids, f"{location}.edges.id")

    analogies = _require_array(logic["analogies"], f"{location}.analogies", 0, 3)
    analogy_ids = []
    for index, analogy in enumerate(analogies):
        _validate_analogy(analogy, index, node_id_set, sentence_map, location)
        analogy_ids.append(analogy["id"])
    _require_unique(analogy_ids, f"{location}.analogies.id")

    rendering = _require_object(logic["rendering"], f"{location}.rendering")
    _require_exact_keys(rendering, RENDERING_KEYS, f"{location}.rendering")
    if rendering["layout"] not in LAYOUTS:
        _fail(f"{location}.rendering.layout", f"허용되지 않은 값입니다: {rendering['layout']}")
    order = _require_array(rendering["reading_order"], f"{location}.rendering.reading_order", 3, 5)
    for index, node_id in enumerate(order):
        _require_string(node_id, f"{location}.rendering.reading_order[{index}]", pattern=NODE_ID_RE)
    _require_unique(order, f"{location}.rendering.reading_order")
    if set(order) != node_id_set:
        _fail(f"{location}.rendering.reading_order", "모든 node ID를 정확히 한 번씩 포함해야 합니다.")

    groups = _require_array(rendering["groups"], f"{location}.rendering.groups", 0, 5)
    group_ids = []
    for index, group in enumerate(groups):
        group_location = f"{location}.rendering.groups[{index}]"
        _require_object(group, group_location)
        _require_exact_keys(group, GROUP_KEYS, group_location)
        group_ids.append(_require_string(group["id"], f"{group_location}.id", pattern=GROUP_ID_RE))
        _require_string(group["label"], f"{group_location}.label", maximum=24)
        group_nodes = _require_array(group["node_ids"], f"{group_location}.node_ids", 1, 5)
        _require_unique(group_nodes, f"{group_location}.node_ids")
        for node_id in group_nodes:
            if node_id not in node_id_set:
                _fail(f"{group_location}.node_ids", f"존재하지 않는 node를 참조합니다: {node_id}")
    _require_unique(group_ids, f"{location}.rendering.groups.id")

    if rendering["target"] != TARGET:
        _fail(f"{location}.rendering.target", f"{TARGET}만 허용됩니다.")
    if rendering["show_title"] is not False:
        _fail(f"{location}.rendering.show_title", "이미지 제목 표시 계약 위반: false여야 합니다.")

    _validate_graph_shape(logic, node_id_set, location)
    return logic


@lru_cache(maxsize=32)
def _font(path: Path, size: int):
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.truetype("malgun.ttf", size=size)


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _wrap(draw, text, font, max_width, max_lines=3):
    words = str(text).split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    expanded = []
    for line in lines:
        if _text_width(draw, line, font) <= max_width:
            expanded.append(line)
            continue
        current = ""
        for char in line:
            candidate = current + char
            if current and _text_width(draw, candidate, font) > max_width:
                expanded.append(current)
                current = char
            else:
                current = candidate
        if current:
            expanded.append(current)
    if len(expanded) > max_lines:
        # Schema limits keep this rare; preserve meaning by shrinking at the caller instead of ellipsis.
        return expanded
    return expanded


def _sentences_badge(numbers):
    numeric = [int(number) for number in numbers]
    if len(numeric) > 1 and numeric == list(range(numeric[0], numeric[-1] + 1)):
        return f"문장 {numeric[0]}–{numeric[-1]}"
    return "문장 " + "·".join(str(number) for number in numbers)


def _node_text(draw, node, width):
    font = _font(FONT_REGULAR, 32)
    lines = _wrap(draw, node["label"], font, width - 52)
    if len(lines) > 2:
        font = _font(FONT_REGULAR, 27)
        lines = _wrap(draw, node["label"], font, width - 52)
    step = 41 if font.size >= 30 else 36
    height = 72 + (len(lines) - 1) * step + draw.textbbox((0, 0), lines[-1], font=font)[3] + 12
    return font, lines, step, height


def _draw_bounded_text(draw, xy, text, font, fill, box, location):
    bounds = draw.textbbox(xy, text, font=font)
    if not (box[0] <= bounds[0] <= bounds[2] <= box[2]
            and box[1] <= bounds[1] <= bounds[3] <= box[3]):
        _fail(location, f"텍스트가 표시 영역을 초과합니다: {text}")
    draw.text(xy, text, font=font, fill=fill)


def _draw_node(draw, box, node, alternate=False):
    x1, y1, x2, y2 = box
    fill = COLORS["node_fill_alt"] if alternate else COLORS["node_fill"]
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=COLORS["node_border"], width=3)

    badge_font = _font(FONT_BOLD, 24)
    role_font = _font(FONT_BOLD, 27)
    badge = _sentences_badge(node["sentence_numbers"])
    badge_width = _text_width(draw, badge, badge_font) + 34
    badge_box = (x1 + 24, y1 + 18, x1 + 24 + badge_width, y1 + 58)
    draw.rounded_rectangle(badge_box, radius=18, fill=COLORS["badge_fill"])
    _draw_bounded_text(draw, (badge_box[0] + 17, badge_box[1] + 5), badge,
                       badge_font, COLORS["badge_ink"], badge_box, node["id"])
    role_x = badge_box[2] + 24
    for size in range(27, 17, -1):
        role_font = _font(FONT_BOLD, size)
        if _text_width(draw, node["role"], role_font) <= x2 - role_x - 24:
            break
    _draw_bounded_text(draw, (role_x, y1 + 21), node["role"], role_font,
                       COLORS["role"], box, node["id"])

    label_font, lines, line_height, _ = _node_text(draw, node, x2 - x1)
    start_y = y1 + 72
    for line_index, line in enumerate(lines):
        _draw_bounded_text(draw, (x1 + 26, start_y + line_index * line_height), line,
                           label_font, COLORS["ink"], box, node["id"])


def _line_color(relation):
    if relation == "CAUSE":
        return COLORS["cause"]
    if relation == "CONTRAST":
        return COLORS["contrast"]
    return COLORS["edge"]


def _segment_points(start, end, dash_pattern):
    x1, y1 = start
    x2, y2 = end
    distance = math.hypot(x2 - x1, y2 - y1)
    if distance == 0:
        return []
    ux, uy = (x2 - x1) / distance, (y2 - y1) / distance
    result = []
    cursor = 0.0
    draw_segment = True
    pattern_index = 0
    while cursor < distance:
        length = dash_pattern[pattern_index % len(dash_pattern)]
        next_cursor = min(distance, cursor + length)
        if draw_segment:
            result.append(((x1 + ux * cursor, y1 + uy * cursor),
                           (x1 + ux * next_cursor, y1 + uy * next_cursor)))
        cursor = next_cursor
        draw_segment = not draw_segment
        pattern_index += 1
    return result


def _draw_polyline(draw, points, relation, possible=False, width=5):
    color = _line_color(relation)
    if relation == "CONTRAST":
        pattern = (18, 11)
    elif relation in {"EXAMPLE", "ANALOGY"}:
        pattern = (6, 9)
    elif relation == "PROBLEM_SOLUTION" or possible:
        pattern = (24, 9, 6, 9)
    else:
        pattern = None

    for start, end in zip(points, points[1:]):
        if pattern:
            for a, b in _segment_points(start, end, pattern):
                draw.line((a, b), fill=color, width=width)
        else:
            draw.line((start, end), fill=color, width=width)

    start, end = points[-2], points[-1]
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 17
    left = (end[0] - size * math.cos(angle - math.pi / 6), end[1] - size * math.sin(angle - math.pi / 6))
    right = (end[0] - size * math.cos(angle + math.pi / 6), end[1] - size * math.sin(angle + math.pi / 6))
    draw.polygon((end, left, right), fill=color)


def _edge_is_possible(edge):
    if any(marker in edge["label"].casefold() for marker in ("수 있", "가능", "may")):
        return True
    return any(" may " in f" {_normalized_evidence(item['quote'])} " for item in edge["evidence"])


def _edge_caption(edge):
    relation = RELATION_KO[edge["relation"]]
    if edge["relation"] == "CAUSE" and _edge_is_possible(edge):
        relation = "가능 인과"
    return f"{relation} · {edge['label']}"


def _label_text(draw, edges, max_width):
    multiple = len(edges) > 1
    font = _font(FONT_BOLD, 20 if multiple else 23)
    lines = [line for edge in edges
             for line in _wrap(draw, _edge_caption(edge), font, max_width - 32, max_lines=2)]
    if len(lines) > 2 and not multiple:
        font = _font(FONT_BOLD, 20)
        lines = _wrap(draw, _edge_caption(edges[0]), font, max_width - 32, max_lines=3)
    line_height = 28 if multiple else 31
    width = min(max_width, max(_text_width(draw, line, font) for line in lines) + 32)
    height = len(lines) * line_height + 18
    return font, lines, line_height, width, height


def _draw_edge_label(draw, center, edges, max_width=560):
    font, lines, line_height, width, height = _label_text(draw, edges, max_width)
    x1, y1 = center[0] - width / 2, center[1] - height / 2
    box = (x1, y1, x1 + width, y1 + height)
    draw.rounded_rectangle(box, radius=13, fill=COLORS["label_fill"], outline=COLORS["label_border"], width=2)
    for index, line in enumerate(lines):
        _draw_bounded_text(draw, (x1 + 16, y1 + 7 + index * line_height), line,
                           font, COLORS["ink"], box, ", ".join(edge["id"] for edge in edges))


def _flow_layout(draw, logic, reserve_backward=False):
    order = logic["rendering"]["reading_order"]
    nodes = {node['id']: node for node in logic['nodes']}
    left, right = (430 if reserve_backward else 230), 1570
    heights = [_node_text(draw, nodes[n], right - left)[3] for n in order]
    pairs = {}
    for edge in logic['edges']:
        pairs.setdefault(frozenset((edge['from'], edge['to'])), []).append(edge)
    gaps = [_label_text(draw, pairs[frozenset(pair)], 580)[4] + 28
            for pair in zip(order, order[1:])]
    spare = (1028 - sum(heights) - sum(gaps)) / (len(order) - 1)
    if spare < 0:
        _fail('논리_시각화', 'FLOW의 본문과 관계 설명이 A4 반쪽 영역을 초과합니다.')
    boxes, y = {}, 16
    for index, node_id in enumerate(order):
        boxes[node_id] = (left, y, right, y + heights[index])
        if index < len(gaps):
            y += heights[index] + gaps[index] + spare
    return boxes


def _branch_layout(logic, reserve_backward=False):
    order = logic["rendering"]["reading_order"]
    order_index = {node_id: index for index, node_id in enumerate(order)}
    neighbors = {node_id: set() for node_id in order}
    for edge in logic["edges"]:
        neighbors[edge["from"]].add(edge["to"])
        neighbors[edge["to"]].add(edge["from"])
    branch = next(
        (node_id for node_id in order
         if sum(order_index[neighbor] > order_index[node_id] for neighbor in neighbors[node_id]) > 1),
        max(order, key=lambda node_id: len(neighbors[node_id])),
    )
    merge = next(
        (node_id for node_id in order[order_index[branch] + 1:]
         if sum(order_index[neighbor] < order_index[node_id] for neighbor in neighbors[node_id]) > 1),
        order[-1],
    )
    branch_index, merge_index = order.index(branch), order.index(merge)
    arms = order[branch_index + 1:merge_index]
    diamond_nodes = {branch, merge, *arms}
    local_pairs = {frozenset((edge["from"], edge["to"])) for edge in logic["edges"]
                   if edge["from"] in diamond_nodes and edge["to"] in diamond_nodes}
    diamond_pairs = {frozenset(pair) for arm in arms for pair in ((branch, arm), (arm, merge))}
    if len(arms) == 2 and local_pairs == diamond_pairs and not reserve_backward:
        # Parallel examples share a row so their connections never pass behind each other.
        rows = [[node_id] for node_id in order[:branch_index + 1]]
        rows += [arms] + [[node_id] for node_id in order[merge_index:]]
        heights = [180 if len(row) == 2 else 128 for row in rows]
        gap = (CANVAS_SIZE[1] - 44 - sum(heights)) / (len(rows) - 1)
        boxes = {}
        y = 22
        for row, height in zip(rows, heights):
            for column, node_id in enumerate(row):
                left, right = (285, 1515) if len(row) == 1 else ((70, 720) if column == 0 else (1080, 1730))
                boxes[node_id] = (left, int(y), right, int(y) + height)
            y += height + gap
        return boxes, branch, merge
    count = len(order)
    node_height = 128
    top, bottom = 22, CANVAS_SIZE[1] - 22
    gap = (bottom - top - count * node_height) / max(1, count - 1)
    boxes = {}
    for index, node_id in enumerate(order):
        y = int(top + index * (node_height + gap))
        if branch_index < index < merge_index:
            left, right = 95, 1175
        else:
            left, right = 285, 1515
        boxes[node_id] = (max(left, 430) if reserve_backward else left, y, right, y + node_height)
    return boxes, branch, merge


def _column_layout(logic, reserve_backward=False):
    order = logic["rendering"]["reading_order"]
    boxes = {}
    node_height = 190
    rows = math.ceil(len(order) / 2)
    top = 180 if reserve_backward else 35
    gap = (CANVAS_SIZE[1] - top - 35 - rows * node_height) / max(1, rows - 1)
    for index, node_id in enumerate(order):
        row, col = divmod(index, 2)
        y = int(top + row * (node_height + gap))
        # Leave room for a wrapped relation caption between the two columns.
        x1 = 70 if col == 0 else 1080
        boxes[node_id] = (x1, y, x1 + 650, y + node_height)
    return boxes


def _box_center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _overlaps(a, b, margin=0):
    return (a[0] < b[2] + margin and b[0] < a[2] + margin
            and a[1] < b[3] + margin and b[1] < a[3] + margin)


def _crosses(a, b, box):
    if a[0] == b[0]:
        return (box[0] < a[0] < box[2]
                and max(min(a[1], b[1]), box[1]) < min(max(a[1], b[1]), box[3]))
    return (box[1] < a[1] < box[3]
            and max(min(a[0], b[0]), box[0]) < min(max(a[0], b[0]), box[2]))


def _path_crosses(points, box):
    return any(_crosses(a, b, box) for a, b in zip(points, points[1:]))


def _shared_segment(first, second):
    for a, b in zip(first, first[1:]):
        for c, d in zip(second, second[1:]):
            if a[0] == b[0] == c[0] == d[0]:
                if max(min(a[1], b[1]), min(c[1], d[1])) < min(max(a[1], b[1]), max(c[1], d[1])):
                    return True
            elif a[1] == b[1] == c[1] == d[1]:
                if max(min(a[0], b[0]), min(c[0], d[0])) < min(max(a[0], b[0]), max(c[0], d[0])):
                    return True
    return False


def _fit_boxes(draw, logic, boxes):
    nodes = {node['id']: node for node in logic['nodes']}
    rows = {}
    for node_id, box in boxes.items():
        rows.setdefault(box[1], []).append(node_id)
    heights = [max(max(boxes[n][3] - boxes[n][1],
                       _node_text(draw, nodes[n], boxes[n][2] - boxes[n][0])[3]) for n in row)
               for row in rows.values()]
    if all(height == boxes[row[0]][3] - boxes[row[0]][1]
           for row, height in zip(rows.values(), heights)):
        return boxes
    gap = (1016 - sum(heights)) / (len(rows) - 1)
    if gap < 36:
        return None
    result, y = {}, 22
    for row, height in zip(rows.values(), heights):
        for node_id in row:
            old = boxes[node_id]
            result[node_id] = (old[0], y, old[2], y + height)
        y += height + gap
    return result


def _route_candidates(draw, boxes, edges, group_index):
    source, target = boxes[edges[0]['from']], boxes[edges[0]['to']]
    # A different port per edge prevents separate relationships becoming one apparent line.
    offset = (group_index - 3) * 12

    def ports(box):
        x, y = _box_center(box)
        return [((x + offset, box[3]), (0, 1)), ((x + offset, box[1]), (0, -1)),
                ((box[2], y + offset), (1, 0)), ((box[0], y + offset), (-1, 0))]

    xs = sorted({35, 225, 1575, 1765,
                 *(b[0] - 24 for b in boxes.values()), *(b[2] + 24 for b in boxes.values())})
    ys = sorted({22, 1038, *(b[1] - 24 for b in boxes.values()),
                 *(b[3] + 24 for b in boxes.values())})
    measures = [(w, *_label_text(draw, edges, w)[3:]) for w in (580, 440, 320)]
    candidates, seen = [], set()
    for (start, sv) in ports(source):
        for (end, tv) in ports(target):
            paths = [[start, (start[0], end[1]), end], [start, (end[0], start[1]), end]]
            paths += [[start, (x, start[1]), (x, end[1]), end] for x in xs if 18 <= x <= 1782]
            paths += [[start, (start[0], y), (end[0], y), end] for y in ys if 18 <= y <= 1042]
            for raw in paths:
                points = []
                for point in raw:
                    if not points or point != points[-1]:
                        points.append(point)
                if len(points) < 2:
                    continue
                if ((points[1][0] - start[0]) * sv[0] + (points[1][1] - start[1]) * sv[1] <= 0
                        or (points[-2][0] - end[0]) * tv[0] + (points[-2][1] - end[1]) * tv[1] < 22):
                    continue
                key = tuple(points)
                if key in seen or any(_path_crosses(points, b) for b in boxes.values()):
                    continue
                seen.add(key)
                length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(points, points[1:]))
                for a, b in zip(points, points[1:]):
                    vertical = a[0] == b[0]
                    low, high = sorted((a[1], b[1]) if vertical else (a[0], b[0]))
                    for max_width, width, height in measures:
                        half = height / 2 if vertical else width / 2
                        end_axis = end[1] if vertical else end[0]
                        lo = low + half + (20 if b == end and end_axis == low else 8)
                        hi = high - half - (20 if b == end and end_axis == high else 8)
                        if lo > hi:
                            continue
                        positions = [(lo + hi) / 2, lo, hi]
                        positions += [lo + (hi - lo) * f / 8 for f in range(1, 8)]
                        for pos in positions:
                            cx = min(1780 - width / 2, max(20 + width / 2, a[0])) if vertical else pos
                            cy = pos if vertical else a[1]
                            box = (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
                            if (box[1] < 16 or box[3] > 1044
                                    or _overlaps(box, _arrow_bounds(points))
                                    or any(_overlaps(box, n, 8) for n in boxes.values())):
                                continue
                            score = length + 80 * (len(points) - 2) + height * 2
                            score += abs(pos - (low + high) / 2) * .15
                            candidates.append((score, points, (cx, cy), max_width, box))
    candidates.sort(key=lambda c: c[0])
    # shortcut: bounded search for the schema's eight edges; raise clearly if no safe plan fits.
    return candidates[:600]


def _arrow_bounds(points):
    x, y = points[-1]
    return (x - 18, y - 18, x + 18, y + 18)


def _compatible(first, second):
    return (not _overlaps(first[4], second[4], 10)
            and not _path_crosses(first[1], second[4])
            and not _path_crosses(second[1], first[4])
            and not _overlaps(first[4], _arrow_bounds(second[1]))
            and not _overlaps(second[4], _arrow_bounds(first[1]))
            and not _shared_segment(first[1], second[1]))


def _plan_edges(draw, boxes, groups):
    choices = [_route_candidates(draw, boxes, edges, i) for i, edges in enumerate(groups)]
    indices = sorted(range(len(groups)), key=lambda i: len(choices[i]))
    selected, attempts = {}, 0

    def search(depth):
        nonlocal attempts
        if depth == len(indices):
            return True
        index = indices[depth]
        for candidate in choices[index]:
            attempts += 1
            if attempts > 60000:
                return False
            if all(_compatible(candidate, other) for other in selected.values()):
                selected[index] = candidate
                if search(depth + 1):
                    return True
                del selected[index]
        return False

    if search(0):
        return [selected[i] for i in range(len(groups))]
    return None


def _validate_scene(boxes, plans, groups):
    for box in list(boxes.values()) + [plan[4] for plan in plans]:
        if not (0 <= box[0] < box[2] <= CANVAS_SIZE[0] and 0 <= box[1] < box[3] <= CANVAS_SIZE[1]):
            _fail('논리_시각화', '도식의 표시 영역이 캔버스를 초과합니다.')
    for i, plan in enumerate(plans):
        if any(_path_crosses(plan[1], b) or _overlaps(plan[4], b) for b in boxes.values()):
            _fail('논리_시각화', f"{groups[i][0]['id']} 연결선 또는 설명이 노드와 겹칩니다.")
        for other in plans[:i]:
            if not _compatible(plan, other):
                _fail('논리_시각화', f"{groups[i][0]['id']} 연결선 또는 설명이 다른 관계와 겹칩니다.")


def _draw_crossing_gaps(draw, points, previous):
    # A small underpass gap distinguishes a crossing from a shared connection.
    for a, b in zip(points, points[1:]):
        for path in previous:
            for c, d in zip(path, path[1:]):
                if (a[0] == b[0]) == (c[0] == d[0]):
                    continue
                x, y = (a[0], c[1]) if a[0] == b[0] else (c[0], a[1])
                if (min(a[0], b[0]) <= x <= max(a[0], b[0])
                        and min(a[1], b[1]) <= y <= max(a[1], b[1])
                        and min(c[0], d[0]) <= x <= max(c[0], d[0])
                        and min(c[1], d[1]) <= y <= max(c[1], d[1])):
                    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=COLORS['background'])


def render_logic_visualization(passage: dict, output_path: Path | str) -> Path:
    """Validate and render one passage without mutating the input object."""
    logic = validate_logic_visualization(passage)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", CANVAS_SIZE, COLORS["background"])
    draw = ImageDraw.Draw(image)
    layout = logic["rendering"]["layout"]
    order = logic["rendering"]["reading_order"]
    order_index = {node_id: index for index, node_id in enumerate(order)}
    backward_edges = [
        edge for edge in logic["edges"]
        if order_index[edge["from"]] > order_index[edge["to"]]
    ]
    reserve_backward = bool(backward_edges)
    if layout == "FLOW":
        boxes = _flow_layout(draw, logic, reserve_backward=reserve_backward)
    elif layout == "BRANCH":
        boxes, _, _ = _branch_layout(logic, reserve_backward=reserve_backward)
    else:
        boxes = _column_layout(logic, reserve_backward=reserve_backward)

    nodes_by_id = {node["id"]: node for node in logic["nodes"]}
    edge_groups = {}
    for edge in logic["edges"]:
        edge_groups.setdefault((edge["from"], edge["to"]), []).append(edge)
    groups = list(edge_groups.values())
    boxes = _fit_boxes(draw, logic, boxes)
    plans = _plan_edges(draw, boxes, groups) if boxes else None
    if plans is None and layout == "BRANCH":
        # Complex forks need space on both sides, while reading_order stays unchanged.
        step = 888 / (len(order) - 1)
        boxes = {node_id: (480, 22 + i * step, 1320, 150 + i * step)
                 for i, node_id in enumerate(order)}
        boxes = _fit_boxes(draw, logic, boxes)
        plans = _plan_edges(draw, boxes, groups) if boxes else None
    if plans is None:
        _fail("논리_시각화", "상자와 관계 설명을 겹치지 않게 배치할 수 없습니다. "
              + "관계: " + ", ".join(edge["id"] for edge in logic["edges"]))
    _validate_scene(boxes, plans, groups)
    previous = []
    for edges, plan in zip(groups, plans):
        edge = edges[0]
        _draw_crossing_gaps(draw, plan[1], previous)
        _draw_polyline(draw, plan[1], edge["relation"], possible=_edge_is_possible(edge))
        previous.append(plan[1])
    for edges, plan in zip(groups, plans):
        _draw_edge_label(draw, plan[2], edges, max_width=plan[3])

    for index, node_id in enumerate(order):
        _draw_node(draw, boxes[node_id], nodes_by_id[node_id], alternate=index % 2 == 1)

    image.save(output_path, format="PNG", optimize=True, dpi=(220, 220))
    return output_path


__all__ = [
    "LogicValidationError",
    "render_logic_visualization",
    "validate_logic_visualization",
]
