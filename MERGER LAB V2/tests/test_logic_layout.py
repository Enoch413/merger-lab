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


if __name__ == "__main__":
    unittest.main(verbosity=2)
