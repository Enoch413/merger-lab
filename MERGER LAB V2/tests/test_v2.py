"""MERGER LAB V2 required matrix and regression checks."""

from __future__ import annotations

import copy
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUTPUTS = ROOT / "test_outputs" / "matrix"
sys.path.insert(0, str(ROOT))

import MERGER_LAB_SERVER as server  # noqa: E402
from hwpx_logic_embedder import NS, validate_hwpx_image_references  # noqa: E402
from logic_visualizer import validate_logic_visualization  # noqa: E402


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))


def payload_in_order(*names):
    passages = []
    for number, name in enumerate(names, start=1):
        passage = copy.deepcopy(load_fixture(name)["PASSAGES"][0])
        passage["번호"] = str(number)
        passages.append(passage)
    return {"PASSAGES": passages}


def unpack_bundle(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        merged_bytes = archive.read("MASTER_ANALYSIS_merged.json")
        hwpx_name = next(name for name in archive.namelist() if name.endswith(".hwpx"))
        hwpx = archive.read(hwpx_name)
        diagrams = {name: archive.read(name) for name in archive.namelist() if name.startswith("diagrams/")}
    with zipfile.ZipFile(io.BytesIO(hwpx)) as archive:
        section = etree.fromstring(archive.read("Contents/section0.xml"))
        header = etree.fromstring(archive.read("Contents/header.xml"))
        content = etree.fromstring(archive.read("Contents/content.hpf"))
    return json.loads(merged_bytes), hwpx, section, header, content, diagrams


def write_matrix_output(name, bundle):
    _, hwpx, _, _, _, diagrams = unpack_bundle(bundle)
    (OUTPUTS / f"{name}.hwpx").write_bytes(hwpx)
    for diagram_name, data in diagrams.items():
        suffix = Path(diagram_name).name
        (OUTPUTS / f"{name}_{suffix}").write_bytes(data)


def top_level_text(element):
    return "".join((node.text or "") for node in element.findall(".//hp:t", NS)).strip()


def page_header_pairs(section):
    pairs = []
    for header in section.findall(".//hp:header", NS):
        values = {}
        for paragraph in header.findall(".//hp:p", NS):
            para_pr_id = paragraph.get("paraPrIDRef")
            if para_pr_id in ("2", "3"):
                values[para_pr_id] = "".join(
                    node.text or "" for node in paragraph.findall("./hp:run/hp:t", NS)
                )
        pairs.append((values.get("2", ""), values.get("3", "")))
    return pairs


def normalize_legacy_section(section):
    result = copy.deepcopy(section)
    for element in list(result):
        text = top_level_text(element)
        has_logic_picture = any(
            (image.get("binaryItemIDRef") or "").startswith("logic_")
            for image in element.findall(".//hc:img", NS)
        )
        if text.startswith("05 ·") or has_logic_picture:
            result.remove(element)
    children = list(result)
    while children:
        element = children[-1]
        if top_level_text(element) or element.findall(".//hp:tbl", NS) or element.findall(".//hp:ctrl", NS):
            break
        result.remove(element)
        children.pop()
    return result


class V2MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUTS.mkdir(parents=True, exist_ok=True)

    def _assert_v2_bundle(self, bundle, payload, passage_count):
        merged, hwpx, section, _, _, diagrams = unpack_bundle(bundle)
        self.assertEqual(merged, payload)
        self.assertEqual(len(section.findall(".//hp:tbl", NS)), passage_count * 6)
        headings = [top_level_text(element) for element in section if top_level_text(element).startswith("05 ·")]
        self.assertEqual(headings, ["05 · 지문 논리 한눈에 보기"] * passage_count)
        self.assertEqual(len(diagrams), passage_count)
        report = validate_hwpx_image_references(hwpx)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["logic_image_references"], [f"logic_{index:03d}" for index in range(1, passage_count + 1)])
        for picture in section.findall(".//hp:pic", NS):
            image = picture.find("./hc:img", NS)
            if image is not None and (image.get("binaryItemIDRef") or "").startswith("logic_"):
                size = picture.find("./hp:sz", NS)
                self.assertEqual((size.get("width"), size.get("height")), ("48135", "28500"))

    def test_t01_to_t04_single_passage_both_pronunciation_options(self):
        cases = [
            ("T01_microwave_excluded", "microwave_APPROVED_MASTER_ANALYSIS.json", "excluded"),
            ("T02_microwave_included", "microwave_APPROVED_MASTER_ANALYSIS.json", "included"),
            ("T03_grief_excluded", "grief_APPROVED_MASTER_ANALYSIS.json", "excluded"),
            ("T04_grief_included", "grief_APPROVED_MASTER_ANALYSIS.json", "included"),
        ]
        for output_name, fixture, pronunciation in cases:
            with self.subTest(case=output_name):
                payload = payload_in_order(fixture)
                bundle, _ = server.build_bundle(payload, pronunciation, "v2")
                self._assert_v2_bundle(bundle, payload, 1)
                write_matrix_output(output_name, bundle)

    def test_t05_to_t08_multiple_passages_preserve_order_and_unique_images(self):
        microwave = "microwave_APPROVED_MASTER_ANALYSIS.json"
        grief = "grief_APPROVED_MASTER_ANALYSIS.json"
        cases = [
            ("T05_microwave_grief_excluded", (microwave, grief), "excluded"),
            ("T06_microwave_grief_included", (microwave, grief), "included"),
            ("T07_grief_microwave_excluded", (grief, microwave), "excluded"),
            ("T08_grief_microwave_included", (grief, microwave), "included"),
        ]
        for output_name, fixtures, pronunciation in cases:
            with self.subTest(case=output_name):
                payload = payload_in_order(*fixtures)
                bundle, _ = server.build_bundle(payload, pronunciation, "v2")
                self._assert_v2_bundle(bundle, payload, 2)
                merged, _, _, _, _, diagrams = unpack_bundle(bundle)
                self.assertEqual([item["논리_시각화"]["rendering"]["layout"] for item in merged["PASSAGES"]],
                                 ["FLOW" if name.startswith("microwave") else "BRANCH" for name in fixtures])
                self.assertNotEqual(diagrams["diagrams/logic_001.png"], diagrams["diagrams/logic_002.png"])
                write_matrix_output(output_name, bundle)

    def test_t09_legacy_compatibility_mode(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        passage = payload["PASSAGES"][0]
        del passage["논리_시각화"]
        for sentence in passage["지문"]:
            sentence.pop("한글발음", None)
        bundle, _ = server.build_bundle(payload, "excluded", "compatibility")
        merged, hwpx, section, _, _, diagrams = unpack_bundle(bundle)
        self.assertEqual(merged, payload)
        self.assertFalse(diagrams)
        self.assertNotIn("05 · 지문 논리 한눈에 보기", "".join(section.itertext()))
        self.assertFalse(validate_hwpx_image_references(hwpx)["logic_image_references"])
        write_matrix_output("T09_legacy_compatibility", bundle)

    def test_t10_invalid_edge_reference(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        payload["PASSAGES"][0]["논리_시각화"]["edges"][0]["to"] = "N999"
        with self.assertRaisesRegex(ValueError, "존재하지 않는 node.*N999"):
            server.build_bundle(payload, "excluded", "v2")

    def test_t11_invalid_image_reference_detector(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        bundle, _ = server.build_bundle(payload, "excluded", "v2")
        _, hwpx, _, _, _, _ = unpack_bundle(bundle)
        with zipfile.ZipFile(io.BytesIO(hwpx)) as source:
            files = {name: source.read(name) for name in source.namelist()}
        section = etree.fromstring(files["Contents/section0.xml"])
        logic_image = next(
            image for image in section.findall(".//hc:img", NS)
            if (image.get("binaryItemIDRef") or "").startswith("logic_")
        )
        logic_image.set("binaryItemIDRef", "logic_missing")
        files["Contents/section0.xml"] = etree.tostring(section, xml_declaration=True, encoding="UTF-8", standalone=True)
        corrupted = io.BytesIO()
        with zipfile.ZipFile(corrupted, "w", zipfile.ZIP_DEFLATED) as target:
            target.writestr("mimetype", files.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
            for name, data in files.items():
                target.writestr(name, data)
        report = validate_hwpx_image_references(corrupted.getvalue())
        self.assertFalse(report["ok"])
        self.assertTrue(any("manifest에 없는 이미지 참조" in error for error in report["errors"]))

    def test_t12_missing_logic_in_v2(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        del payload["PASSAGES"][0]["논리_시각화"]
        with self.assertRaisesRegex(ValueError, "V2 모드에 필요한 데이터가 누락"):
            server.build_bundle(payload, "excluded", "v2")

    def test_school_and_range_are_hwpx_only(self):
        payload = payload_in_order(
            "microwave_APPROVED_MASTER_ANALYSIS.json",
            "grief_APPROVED_MASTER_ANALYSIS.json",
        )
        bundle, _ = server.build_bundle(
            payload,
            "included",
            "v2",
            school="한빛고등학교",
            range_text="1학기 중간고사 1~3강",
        )
        merged, _, section, _, _, _ = unpack_bundle(bundle)
        self.assertEqual(merged, payload)
        self.assertNotIn("학교", merged)
        self.assertNotIn("범위", merged)
        self.assertEqual(
            page_header_pairs(section),
            [("한빛고등학교", "1학기 중간고사 1~3강")] * 2,
        )
        write_matrix_output("T13_school_range_included", bundle)

    def test_school_and_range_validation(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        with self.assertRaisesRegex(ValueError, "학교.*문자열"):
            server.build_bundle(payload, school=123)
        with self.assertRaisesRegex(ValueError, "범위.*줄바꿈"):
            server.build_bundle(payload, range_text="1학기\n중간고사")
        with self.assertRaisesRegex(ValueError, "학교.*40자"):
            server.build_bundle(payload, school="가" * 41)

    def test_range_rules_apply_by_final_passage_number(self):
        example_map = server.build_range_map(
            [{"번호": str(number)} for number in range(1, 21)],
            range_rules=[
                {"start": 1, "end": 10, "text": "Q미니S 10강"},
                {"start": 11, "end": 20, "text": "Q미니S 11강"},
            ],
        )
        self.assertEqual(example_map, ["Q미니S 10강"] * 10 + ["Q미니S 11강"] * 10)

        payload = payload_in_order(
            "microwave_APPROVED_MASTER_ANALYSIS.json",
            "grief_APPROVED_MASTER_ANALYSIS.json",
            "microwave_APPROVED_MASTER_ANALYSIS.json",
            "grief_APPROVED_MASTER_ANALYSIS.json",
        )
        rules = [
            {"start": 1, "end": 2, "text": "Q미니S 10강"},
            {"start": 3, "end": 4, "text": "Q미니S 11강"},
        ]
        bundle, _ = server.build_bundle(
            payload,
            "excluded",
            "compatibility",
            school="한빛고등학교",
            range_rules=rules,
        )
        merged, _, section, _, _, _ = unpack_bundle(bundle)
        self.assertEqual(merged, payload)
        self.assertEqual(
            page_header_pairs(section),
            [
                ("한빛고등학교", "Q미니S 10강"),
                ("한빛고등학교", "Q미니S 10강"),
                ("한빛고등학교", "Q미니S 11강"),
                ("한빛고등학교", "Q미니S 11강"),
            ],
        )

        with self.assertRaisesRegex(ValueError, "범위 구간이 겹칩니다.*지문 2"):
            server.build_bundle(payload, range_rules=[
                {"start": 1, "end": 2, "text": "10강"},
                {"start": 2, "end": 4, "text": "11강"},
            ])
        with self.assertRaisesRegex(ValueError, "범위가 지정되지 않은 지문.*3, 4"):
            server.build_bundle(payload, range_rules=[
                {"start": 1, "end": 2, "text": "10강"},
            ])
        with self.assertRaisesRegex(ValueError, "지문 번호는 1~4 안"):
            server.build_bundle(payload, range_rules=[
                {"start": 1, "end": 5, "text": "10강"},
            ])

    def test_required_invalid_logic_cases(self):
        def invalid(mutator):
            payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
            mutator(payload["PASSAGES"][0]["논리_시각화"])
            return payload

        cases = [
            ("nodes 누락", lambda logic: logic.pop("nodes"), "필수 키.*nodes"),
            ("edges 누락", lambda logic: logic.pop("edges"), "필수 키.*edges"),
            ("relation 오류", lambda logic: logic["edges"][0].update(relation="UNKNOWN"), "relation.*허용되지 않은"),
            ("reading_order 오류", lambda logic: logic["rendering"].update(reading_order=["N1", "N2", "N3", "N4", "N4"]), "중복 값"),
            ("인용문 오류", lambda logic: logic["nodes"][0]["evidence"][0].update(quote="NOT IN ORIGINAL"), "인용문이 원문"),
            ("FLOW 분기", lambda logic: logic["edges"][3].update(**{"from": "N3", "to": "N5"}), "FLOW인데 실제 그래프가 분기형"),
            ("제목 계약", lambda logic: logic["rendering"].update(show_title=True), "제목 표시 계약 위반"),
            ("target 오류", lambda logic: logic["rendering"].update(target="A4_FULL_PAGE"), "A4_HALF_PAGE만 허용"),
        ]
        for name, mutator, message in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, message):
                    server.build_bundle(invalid(mutator), "excluded", "v2")

        payload = payload_in_order("grief_APPROVED_MASTER_ANALYSIS.json")
        logic = payload["PASSAGES"][0]["논리_시각화"]
        logic["edges"] = [edge for edge in logic["edges"] if edge["id"] != "E4"]
        with self.assertRaisesRegex(ValueError, "BRANCH인데 실제 그래프에 분기 Edge가 없습니다"):
            server.build_bundle(payload, "excluded", "v2")

    def test_approved_graph_contracts_and_probability(self):
        microwave = load_fixture("microwave_APPROVED_MASTER_ANALYSIS.json")["PASSAGES"][0]["논리_시각화"]
        grief = load_fixture("grief_APPROVED_MASTER_ANALYSIS.json")["PASSAGES"][0]["논리_시각화"]
        self.assertEqual([(edge["from"], edge["to"]) for edge in microwave["edges"]],
                         [("N1", "N2"), ("N2", "N3"), ("N3", "N4"), ("N4", "N5")])
        self.assertEqual([(edge["from"], edge["to"]) for edge in grief["edges"]],
                         [("N1", "N2"), ("N2", "N3"), ("N3", "N4"), ("N2", "N5"), ("N4", "N5")])
        cause = next(edge for edge in grief["edges"] if edge["relation"] == "CAUSE")
        self.assertIn("수 있음", cause["label"])
        self.assertTrue(any("may" in evidence["quote"] for evidence in cause["evidence"]))

    def test_semantic_edges_may_point_against_reading_order(self):
        flow_payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        flow_payload["PASSAGES"][0]["논리_시각화"]["edges"][0].update(**{"from": "N2", "to": "N1"})
        validate_logic_visualization(flow_payload["PASSAGES"][0])

        branch_payload = payload_in_order("grief_APPROVED_MASTER_ANALYSIS.json")
        edges = branch_payload["PASSAGES"][0]["논리_시각화"]["edges"]
        replacements = [
            ("N1", "N2"),
            ("N3", "N1"),
            ("N3", "N4"),
            ("N4", "N5"),
            ("N1", "N5"),
        ]
        for edge, (source, target) in zip(edges, replacements):
            edge.update(**{"from": source, "to": target})

        bundle, _ = server.build_bundle(branch_payload, "excluded", "v2")
        merged, _, _, _, _, diagrams = unpack_bundle(bundle)
        self.assertEqual(merged, branch_payload)
        diagram = diagrams["diagrams/logic_001.png"]
        image = Image.open(io.BytesIO(diagram)).convert("RGB")
        background = image.getpixel((0, 0))
        outer_lane_pixels = sum(
            image.getpixel((x, y)) != background
            for x in range(30, 42)
            for y in range(image.height)
        )
        self.assertGreater(outer_lane_pixels, 100)

    def test_v2_preserves_zero_to_four_from_same_template(self):
        payload = payload_in_order("microwave_APPROVED_MASTER_ANALYSIS.json")
        for pronunciation in ("excluded", "included"):
            with self.subTest(pronunciation=pronunciation):
                compatibility_bundle, _ = server.build_bundle(payload, pronunciation, "compatibility")
                v2_bundle, _ = server.build_bundle(payload, pronunciation, "v2")
                _, _, compatibility_section, compatibility_header, _, _ = unpack_bundle(compatibility_bundle)
                _, _, v2_section, v2_header, _, _ = unpack_bundle(v2_bundle)
                self.assertEqual(
                    etree.tostring(normalize_legacy_section(compatibility_section), method="c14n"),
                    etree.tostring(normalize_legacy_section(v2_section), method="c14n"),
                )
                self.assertEqual(
                    etree.tostring(compatibility_header, method="c14n"),
                    etree.tostring(v2_header, method="c14n"),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
