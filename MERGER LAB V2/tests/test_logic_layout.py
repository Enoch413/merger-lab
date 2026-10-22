"""Keep relation captions readable in two-column logic diagrams."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import logic_visualizer as visualizer


def overlaps(first, second):
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


class ColumnCaptionTests(unittest.TestCase):
    def test_column_captions_do_not_overlap_nodes_or_each_other(self):
        payload = json.loads((ROOT / "tests/fixtures/microwave_APPROVED_MASTER_ANALYSIS.json")
                             .read_text(encoding="utf-8-sig"))
        passage = payload["PASSAGES"][0]
        logic = passage["논리_시각화"]
        extra = copy.deepcopy(logic["edges"][0])
        extra.update(id="E5", **{"from": "N1", "to": "N3"}, relation="ANALOGY",
                     label="줄기에서 가지로 뻗는 회의")
        logic["edges"].append(extra)
        for edge, label in zip(logic["edges"], [
            "안건의 존재와 진행의 비선형성", "여러 갈래로 전개되는 구체적 모습",
            "사례를 종합하고 관리자 역할 제시", "변화를 받아들이는 평가로 마무리",
        ]):
            edge.update(relation="ELABORATION", label=label)
        original = copy.deepcopy(passage)
        rounded_rectangle = ImageDraw.ImageDraw.rounded_rectangle

        for layout in ("ANALOGY_MAP", "CONTRAST_COLUMNS"):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as directory:
                logic["rendering"]["layout"] = layout
                labels, nodes = [], []

                def record_rectangle(draw, box, *args, **kwargs):
                    fill = kwargs.get("fill")
                    if fill == visualizer.COLORS["label_fill"]:
                        labels.append(box)
                    elif fill in (visualizer.COLORS["node_fill"], visualizer.COLORS["node_fill_alt"]):
                        nodes.append(box)
                    return rounded_rectangle(draw, box, *args, **kwargs)

                with patch.object(ImageDraw.ImageDraw, "rounded_rectangle", record_rectangle):
                    visualizer.render_logic_visualization(passage, Path(directory) / "logic.png")
                self.assertEqual(len(labels), len(logic["edges"]))
                for index, label in enumerate(labels):
                    self.assertGreaterEqual(min(label[:2]), 0)
                    self.assertLessEqual(label[2], visualizer.CANVAS_SIZE[0])
                    self.assertLessEqual(label[3], visualizer.CANVAS_SIZE[1])
                    for node in nodes:
                        self.assertFalse(overlaps(label, node), (layout, label, node))
                    for other in labels[:index]:
                        self.assertFalse(overlaps(label, other), (layout, label, other))
                original["논리_시각화"]["rendering"]["layout"] = layout
                self.assertEqual(passage, original)


class ParallelRelationTests(unittest.TestCase):
    def passage_with_parallel_relations(self, count=2):
        payload = json.loads((ROOT / "tests/fixtures/microwave_APPROVED_MASTER_ANALYSIS.json")
                             .read_text(encoding="utf-8-sig"))
        passage = payload["PASSAGES"][0]
        edges = passage["논리_시각화"]["edges"]
        edges[2].update(relation="SEQUENCE", label="저녁에서 다음 날 아침으로")
        for index in range(count - 1):
            extra = copy.deepcopy(edges[2])
            extra.update(id=f"E{5 + index}", relation="CONTRAST",
                         label="죽었다는 판단과 살아 움직이는 모습")
            edges.append(extra)
        return passage

    def test_parallel_relations_remain_visible_without_overlapping(self):
        rectangle = ImageDraw.ImageDraw.rounded_rectangle
        draw_text = ImageDraw.ImageDraw.text
        for count in (2, 5):
            for backward in (False, True):
                with self.subTest(count=count, backward=backward), tempfile.TemporaryDirectory() as directory:
                    passage = self.passage_with_parallel_relations(count)
                    if backward:
                        for edge in passage["논리_시각화"]["edges"]:
                            if edge["from"] == "N3" and edge["to"] == "N4":
                                edge["from"], edge["to"] = "N4", "N3"
                    original = copy.deepcopy(passage)
                    labels, nodes, text = [], [], []

                    def record_rectangle(draw, box, *args, **kwargs):
                        fill = kwargs.get("fill")
                        if fill == visualizer.COLORS["label_fill"]:
                            labels.append(box)
                        elif fill in (visualizer.COLORS["node_fill"], visualizer.COLORS["node_fill_alt"]):
                            nodes.append(box)
                        return rectangle(draw, box, *args, **kwargs)

                    def record_text(draw, xy, value, *args, **kwargs):
                        text.append(value)
                        return draw_text(draw, xy, value, *args, **kwargs)

                    with patch.object(ImageDraw.ImageDraw, "rounded_rectangle", record_rectangle), \
                            patch.object(ImageDraw.ImageDraw, "text", record_text):
                        visualizer.render_logic_visualization(passage, Path(directory) / "logic.png")
                    self.assertEqual(passage, original)
                    self.assertEqual(len(labels), 4)
                    all_text = "".join("".join(text).split())
                    for edge in passage["논리_시각화"]["edges"]:
                        self.assertIn("".join(visualizer._edge_caption(edge).split()), all_text)
                    for index, label in enumerate(labels):
                        self.assertGreaterEqual(min(label[:2]), 0)
                        self.assertLessEqual(label[2], visualizer.CANVAS_SIZE[0])
                        self.assertLessEqual(label[3], visualizer.CANVAS_SIZE[1])
                        for other in nodes + labels[:index]:
                            self.assertFalse(overlaps(label, other), (label, other))

    def test_parallel_relations_do_not_hide_a_missing_flow_link(self):
        passage = self.passage_with_parallel_relations()
        passage["논리_시각화"]["edges"].pop(0)
        with self.assertRaisesRegex(ValueError, "연속 흐름"):
            visualizer.validate_logic_visualization(passage)

    def test_parallel_relations_alone_are_not_a_branch(self):
        passage = self.passage_with_parallel_relations()
        passage["논리_시각화"]["rendering"]["layout"] = "BRANCH"
        with self.assertRaisesRegex(ValueError, "분기 Edge가 없습니다"):
            visualizer.validate_logic_visualization(passage)


class BranchRoutingTests(unittest.TestCase):
    def test_line_crossing_has_a_visible_underpass_gap(self):
        image = Image.new("RGB", (100, 100), visualizer.COLORS["background"])
        draw = ImageDraw.Draw(image)
        first, second = [(10, 50), (90, 50)], [(50, 10), (50, 90)]
        visualizer._draw_polyline(draw, first, "EVIDENCE")
        visualizer._draw_crossing_gaps(draw, second, [first])
        visualizer._draw_polyline(draw, second, "EVIDENCE")
        self.assertEqual(image.getpixel((44, 50)), image.getpixel((0, 0)))
        self.assertNotEqual(image.getpixel((50, 50)), image.getpixel((0, 0)))
        self.assertNotEqual(image.getpixel((35, 50)), image.getpixel((0, 0)))

    def test_complex_forks_and_backward_columns_preserve_visible_content(self):
        cases = [
            ("BRANCH", [(1, 2), (1, 3), (1, 4), (1, 5)]),
            ("BRANCH", [(1, 2), (1, 3), (2, 3), (2, 4), (3, 4), (4, 5)]),
            ("BRANCH", [(1, 2), (3, 2), (4, 2), (4, 5)]),
            ("BRANCH", [(1, 3), (3, 2), (3, 4), (3, 5), (1, 2)]),
            ("BRANCH", [(1, 2), (3, 2), (2, 4), (4, 5), (3, 5), (3, 4)]),
            ("CONTRAST_COLUMNS", [(1, 2), (1, 3), (3, 2), (4, 1), (4, 5), (5, 2)]),
        ]
        for layout, pairs in cases:
            with self.subTest(layout=layout, pairs=pairs), tempfile.TemporaryDirectory() as directory:
                passage = ParallelRelationTests().passage_with_parallel_relations()
                logic = passage["논리_시각화"]
                logic["rendering"].update(layout=layout, groups=[])
                template = logic["edges"][0]
                logic["edges"] = [dict(copy.deepcopy(template), id=f"E{i}",
                                       **{"from": f"N{a}", "to": f"N{b}"},
                                       label="관계의 구체적인 사례와 그에 대한 설명")
                                  for i, (a, b) in enumerate(pairs, 1)]
                # Forty Korean characters force the narrow branch node to wrap.
                for node in logic["nodes"]:
                    node["label"] = "다양한 상황에 관한 설명과 그 결과를 빠짐없이 확인하는 구체적인 사례"
                original = copy.deepcopy(passage)
                paths, labels, nodes, texts = [], [], {}, []
                node_fn, path_fn = visualizer._draw_node, visualizer._draw_polyline
                rect_fn, text_fn = ImageDraw.ImageDraw.rounded_rectangle, ImageDraw.ImageDraw.text
                current_node = None

                def record_node(draw, box, node, *args, **kwargs):
                    nonlocal current_node
                    nodes[node["id"]] = box
                    current_node = node["id"]
                    node_fn(draw, box, node, *args, **kwargs)
                    current_node = None

                def record_path(draw, points, *args, **kwargs):
                    paths.append(points)
                    path_fn(draw, points, *args, **kwargs)

                def record_rectangle(draw, box, *args, **kwargs):
                    if kwargs.get("fill") == visualizer.COLORS["label_fill"]:
                        labels.append(box)
                    return rect_fn(draw, box, *args, **kwargs)

                def record_text(draw, xy, value, *args, **kwargs):
                    texts.append((current_node, value, draw.textbbox(xy, value, font=kwargs["font"])))
                    return text_fn(draw, xy, value, *args, **kwargs)

                def crosses(a, b, box):
                    if a[0] == b[0]:
                        return box[0] < a[0] < box[2] and max(min(a[1], b[1]), box[1]) < min(max(a[1], b[1]), box[3])
                    self.assertEqual(a[1], b[1])
                    return box[1] < a[1] < box[3] and max(min(a[0], b[0]), box[0]) < min(max(a[0], b[0]), box[2])

                with patch.object(visualizer, "_draw_node", record_node), \
                        patch.object(visualizer, "_draw_polyline", record_path), \
                        patch.object(ImageDraw.ImageDraw, "rounded_rectangle", record_rectangle), \
                        patch.object(ImageDraw.ImageDraw, "text", record_text):
                    visualizer.render_logic_visualization(passage, Path(directory) / "complex.png")
                self.assertEqual(passage, original)
                self.assertEqual(len(paths), len(pairs))
                self.assertEqual(len(labels), len(pairs))
                all_text = "".join("".join(value for _, value, _ in texts).split())
                for edge in logic["edges"]:
                    self.assertIn("".join(visualizer._edge_caption(edge).split()), all_text)
                for node in logic["nodes"]:
                    drawn = [(value, box) for n, value, box in texts if n == node["id"]]
                    self.assertEqual("".join("".join(value for value, _ in drawn[2:]).split()),
                                     "".join(node["label"].split()))
                    box = nodes[node["id"]]
                    for _, t in drawn:
                        self.assertTrue(box[0] <= t[0] <= t[2] <= box[2] and box[1] <= t[1] <= t[3] <= box[3], (box, t))
                for i, points in enumerate(paths):
                    source, target = (nodes[f"N{n}"] for n in pairs[i])
                    self.assertTrue(source[0] <= points[0][0] <= source[2] and source[1] <= points[0][1] <= source[3])
                    self.assertTrue(target[0] <= points[-1][0] <= target[2] and target[1] <= points[-1][1] <= target[3])
                    for a, b in zip(points, points[1:]):
                        for box in list(nodes.values()) + labels[:i] + labels[i + 1:]:
                            self.assertFalse(crosses(a, b, box), (i, points, box))
                for i, label in enumerate(labels):
                    self.assertTrue(0 <= label[0] < label[2] <= 1800 and 0 <= label[1] < label[3] <= 1060)
                    for box in list(nodes.values()) + labels[:i]:
                        self.assertFalse(overlaps(label, box), (label, box))

    def test_unplaceable_scene_fails_without_saving_a_broken_image(self):
        passage = ParallelRelationTests().passage_with_parallel_relations()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "broken.png"
            with patch.object(visualizer, "_plan_edges", return_value=None):
                with self.assertRaisesRegex(ValueError, "E1"):
                    visualizer.render_logic_visualization(passage, output)
            self.assertFalse(output.exists())

    def test_split_and_merge_routes_clear_nodes_and_other_captions(self):
        rectangle = ImageDraw.ImageDraw.rounded_rectangle
        polyline = visualizer._draw_polyline
        for count in (4, 5):
            with self.subTest(nodes=count), tempfile.TemporaryDirectory() as directory:
                payload = json.loads((ROOT / "tests/fixtures/microwave_APPROVED_MASTER_ANALYSIS.json")
                                     .read_text(encoding="utf-8-sig"))
                passage = payload["PASSAGES"][0]
                logic = passage["논리_시각화"]
                logic["nodes"] = logic["nodes"][:count]
                logic["rendering"].update(layout="BRANCH", groups=[],
                                           reading_order=[node["id"] for node in logic["nodes"]])
                pairs = ([("N1", "N2"), ("N1", "N3"), ("N2", "N4"), ("N3", "N4")]
                         if count == 4 else
                         [("N1", "N2"), ("N2", "N3"), ("N2", "N4"), ("N3", "N5"), ("N4", "N5")])
                template = logic["edges"][0]
                logic["edges"] = [dict(copy.deepcopy(template), id=f"E{index}",
                                       **{"from": source, "to": target}, relation="EXAMPLE",
                                       label="문제의 구체적인 사례와 대응 방향")
                                  for index, (source, target) in enumerate(pairs, 1)]
                original = copy.deepcopy(passage)
                paths, nodes, labels, events = [], [], [], []

                def record_rectangle(draw, box, *args, **kwargs):
                    fill = kwargs.get("fill")
                    if fill == visualizer.COLORS["label_fill"]:
                        labels.append(box)
                        events.append("caption")
                    elif fill in (visualizer.COLORS["node_fill"], visualizer.COLORS["node_fill_alt"]):
                        nodes.append(box)
                    return rectangle(draw, box, *args, **kwargs)

                def record_polyline(draw, points, *args, **kwargs):
                    paths.append(points)
                    events.append("line")
                    return polyline(draw, points, *args, **kwargs)

                def crosses(start, end, box):
                    if start[0] == end[0]:
                        return (box[0] < start[0] < box[2]
                                and max(min(start[1], end[1]), box[1]) < min(max(start[1], end[1]), box[3]))
                    self.assertEqual(start[1], end[1])
                    return (box[1] < start[1] < box[3]
                            and max(min(start[0], end[0]), box[0]) < min(max(start[0], end[0]), box[2]))

                with patch.object(ImageDraw.ImageDraw, "rounded_rectangle", record_rectangle), \
                        patch.object(visualizer, "_draw_polyline", record_polyline):
                    visualizer.render_logic_visualization(passage, Path(directory) / "branch.png")
                self.assertEqual(passage, original)
                self.assertEqual(len(paths), len(pairs))
                self.assertEqual(len(labels), len(pairs))
                for points in paths:
                    for start, end in zip(points, points[1:]):
                        for node in nodes:
                            self.assertFalse(crosses(start, end, node), (points, node))
                for index, label in enumerate(labels):
                    for other in nodes + labels[:index]:
                        self.assertFalse(overlaps(label, other), (label, other))
                    for path_index, points in enumerate(paths):
                        if path_index != index:
                            for start, end in zip(points, points[1:]):
                                self.assertFalse(crosses(start, end, label), (points, label))
                self.assertLess(max(i for i, event in enumerate(events) if event == "line"),
                                min(i for i, event in enumerate(events) if event == "caption"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
