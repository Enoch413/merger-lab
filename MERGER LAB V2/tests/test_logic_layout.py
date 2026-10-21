"""Keep relation captions readable in two-column logic diagrams."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageDraw

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
