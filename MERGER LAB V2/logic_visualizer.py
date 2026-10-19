#!/usr/bin/env python3
"""Validate approved V2 logic data and render a print-ready PNG diagram."""

from __future__ import annotations

import math
import re
import unicodedata
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
    actual_pairs = [frozenset((edge["from"], edge["to"])) for edge in edges]
    if layout == "FLOW":
        if any(len(connected) > 2 for connected in neighbors.values()):
            _fail(f"{location}.rendering.layout", "FLOW인데 실제 그래프가 분기형입니다.")
        if len(actual_pairs) != len(expected_pairs) or set(actual_pairs) != expected_pairs:
            _fail(f"{location}.rendering.layout", "FLOW의 Edge가 reading_order의 연속 흐름과 일치하지 않습니다.")
    elif layout == "BRANCH":
        if len(actual_pairs) == len(expected_pairs) and set(actual_pairs) == expected_pairs:
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


def _draw_node(draw, box, node, alternate=False):
    x1, y1, x2, y2 = box
    fill = COLORS["node_fill_alt"] if alternate else COLORS["node_fill"]
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=COLORS["node_border"], width=3)

    badge_font = _font(FONT_BOLD, 24)
    role_font = _font(FONT_BOLD, 27)
    label_font = _font(FONT_REGULAR, 32)
    badge = _sentences_badge(node["sentence_numbers"])
    badge_width = _text_width(draw, badge, badge_font) + 34
    badge_box = (x1 + 24, y1 + 18, x1 + 24 + badge_width, y1 + 58)
    draw.rounded_rectangle(badge_box, radius=18, fill=COLORS["badge_fill"])
    draw.text((badge_box[0] + 17, badge_box[1] + 5), badge, font=badge_font, fill=COLORS["badge_ink"])
    draw.text((badge_box[2] + 24, y1 + 21), node["role"], font=role_font, fill=COLORS["role"])

    max_width = x2 - x1 - 52
    lines = _wrap(draw, node["label"], label_font, max_width, max_lines=2)
    if len(lines) > 2:
        label_font = _font(FONT_REGULAR, 27)
        lines = _wrap(draw, node["label"], label_font, max_width, max_lines=3)
    line_height = 41 if getattr(label_font, "size", 32) >= 30 else 36
    start_y = y1 + 72
    for line_index, line in enumerate(lines[:3]):
        draw.text((x1 + 26, start_y + line_index * line_height), line, font=label_font, fill=COLORS["ink"])


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


def _draw_edge_label(draw, center, edge, max_width=560):
    font = _font(FONT_BOLD, 23)
    caption = _edge_caption(edge)
    lines = _wrap(draw, caption, font, max_width - 32, max_lines=2)
    if len(lines) > 2:
        font = _font(FONT_BOLD, 20)
        lines = _wrap(draw, caption, font, max_width - 32, max_lines=3)
    line_height = 31
    width = min(max_width, max(_text_width(draw, line, font) for line in lines) + 32)
    height = len(lines) * line_height + 18
    x1, y1 = center[0] - width / 2, center[1] - height / 2
    box = (x1, y1, x1 + width, y1 + height)
    draw.rounded_rectangle(box, radius=13, fill=COLORS["label_fill"], outline=COLORS["label_border"], width=2)
    for index, line in enumerate(lines):
        draw.text((x1 + 16, y1 + 7 + index * line_height), line, font=font, fill=COLORS["ink"])


def _flow_layout(logic, reserve_backward=False):
    order = logic["rendering"]["reading_order"]
    count = len(order)
    node_height = 135 if count <= 4 else 128
    top, bottom = 25, CANVAS_SIZE[1] - 28
    gap = (bottom - top - count * node_height) / max(1, count - 1)
    boxes = {}
    left = 430 if reserve_backward else 230
    for index, node_id in enumerate(order):
        y = int(top + index * (node_height + gap))
        boxes[node_id] = (left, y, 1570, y + node_height)
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
    node_height = 150
    rows = math.ceil(len(order) / 2)
    top = 180 if reserve_backward else 35
    gap = (CANVAS_SIZE[1] - top - 35 - rows * node_height) / max(1, rows - 1)
    for index, node_id in enumerate(order):
        row, col = divmod(index, 2)
        y = int(top + row * (node_height + gap))
        x1 = 70 if col == 0 else 930
        boxes[node_id] = (x1, y, x1 + 800, y + node_height)
    return boxes


def _box_center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _route_edge(source_box, target_box, side_route=False, backward_lane=None, backward_axis="left"):
    if backward_lane is not None:
        if backward_axis == "top":
            y = 25 + backward_lane * 18
            start = ((source_box[0] + source_box[2]) / 2, source_box[1])
            end = ((target_box[0] + target_box[2]) / 2, target_box[1])
            return [start, (start[0], y), (end[0], y), end]
        x = 35 + backward_lane * 22
        start = (source_box[0], (source_box[1] + source_box[3]) / 2)
        end = (target_box[0], (target_box[1] + target_box[3]) / 2)
        return [start, (x, start[1]), (x, end[1]), end]
    if side_route:
        x = CANVAS_SIZE[0] - 62
        start = (source_box[2], (source_box[1] + source_box[3]) / 2)
        end = (target_box[2], (target_box[1] + target_box[3]) / 2)
        return [start, (x, start[1]), (x, end[1]), end]
    source_center, target_center = _box_center(source_box), _box_center(target_box)
    if target_box[1] >= source_box[3]:
        start = (source_center[0], source_box[3])
        end = (target_center[0], target_box[1])
        if abs(start[0] - end[0]) < 4:
            return [start, end]
        middle_y = (start[1] + end[1]) / 2
        return [start, (start[0], middle_y), (end[0], middle_y), end]
    start = (source_box[2], source_center[1])
    end = (target_box[0], target_center[1])
    middle_x = (start[0] + end[0]) / 2
    return [start, (middle_x, start[1]), (middle_x, end[1]), end]


def _label_center(points, side_route=False, backward_axis=None):
    if backward_axis == "left":
        vertical_start, vertical_end = points[1], points[2]
        return (225, (vertical_start[1] + vertical_end[1]) / 2)
    if backward_axis == "top":
        horizontal_start, horizontal_end = points[1], points[2]
        return ((horizontal_start[0] + horizontal_end[0]) / 2, 105)
    if side_route:
        vertical_start, vertical_end = points[1], points[2]
        return (vertical_start[0] - 205, (vertical_start[1] + vertical_end[1]) / 2)
    longest = max(zip(points, points[1:]), key=lambda pair: math.hypot(pair[1][0] - pair[0][0], pair[1][1] - pair[0][1]))
    return ((longest[0][0] + longest[1][0]) / 2, (longest[0][1] + longest[1][1]) / 2)


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
        boxes = _flow_layout(logic, reserve_backward=reserve_backward)
        branch_info = None
    elif layout == "BRANCH":
        boxes, branch, merge = _branch_layout(logic, reserve_backward=reserve_backward)
        branch_info = (branch, merge)
    else:
        boxes = _column_layout(logic, reserve_backward=reserve_backward)
        branch_info = None

    nodes_by_id = {node["id"]: node for node in logic["nodes"]}
    backward_lanes = {edge["id"]: index for index, edge in enumerate(backward_edges)}

    for edge in logic["edges"]:
        backward_lane = backward_lanes.get(edge["id"])
        backward_axis = "top" if layout in {"CONTRAST_COLUMNS", "ANALOGY_MAP"} else "left"
        side_route = bool(
            backward_lane is None and branch_info
            and edge["from"] == branch_info[0] and edge["to"] == branch_info[1]
        )
        points = _route_edge(
            boxes[edge["from"]], boxes[edge["to"]],
            side_route=side_route,
            backward_lane=backward_lane,
            backward_axis=backward_axis,
        )
        _draw_polyline(draw, points, edge["relation"], possible=_edge_is_possible(edge))
        if backward_lane is not None:
            center = _label_center(points, backward_axis=backward_axis)
            max_width = 340 if backward_axis == "left" else 520
        else:
            center = _label_center(points, side_route=side_route)
            max_width = 410 if side_route else 580
        _draw_edge_label(draw, center, edge, max_width=max_width)

    for index, node_id in enumerate(order):
        _draw_node(draw, boxes[node_id], nodes_by_id[node_id], alternate=index % 2 == 1)

    image.save(output_path, format="PNG", optimize=True, dpi=(220, 220))
    return output_path


__all__ = [
    "LogicValidationError",
    "render_logic_visualization",
    "validate_logic_visualization",
]
