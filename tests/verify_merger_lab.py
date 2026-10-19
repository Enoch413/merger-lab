"""End-to-end regression checks and shareable sample output files."""

import copy
import io
import json
import sys
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from threading import Thread

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import MERGER_LAB_SERVER as server  # noqa: E402

HP = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
OUTPUTS = ROOT / "test_outputs"


def sample_passage(number, with_pronunciation=True, long=False):
    english = "Students can improve their skills / through regular practice."
    pronunciation = "스튜던츠 캔 임프루브 데어 스킬즈 / 쓰루 레귤러 프랙티스."
    korean = "학생들은 자신의 실력을 향상시킬 수 있다 / 꾸준한 연습을 통해."
    if long:
        english = " / ".join([english] * 7)
        pronunciation = " / ".join([pronunciation] * 7) + "\n" + pronunciation
        korean = " / ".join([korean] * 7) + "\n" + korean
    sentence = {"번호": "1", "영어": english, "한국어": korean}
    if with_pronunciation:
        # Deliberately add it last to test field-name access rather than JSON key order.
        sentence["한글발음"] = pronunciation
    return {
        "번호": str(number),
        "전체_내용": "연습이 실력에 도움이 된다는 글입니다.",
        "배경_지식": [{"제목": "Practice", "내용": "반복의 효과"}],
        "소재": ["practice"],
        "주제": "연습",
        "요지": "계속 연습하면 나아진다 (even when progress is slow).",
        "제목": "The Value of Practice (for Everyone)",
        "한_문장_요약": "연습이 성장에 기여한다.",
        "주제문_번호": "1",
        "지문": [sentence],
        "어휘": [{"단어": "practice", "뜻": "연습", "동의어": "training", "반의어": "neglect", "반의어_뜻": "방치"}],
        "출제포인트": {"핵심 내용 재활용": {"정보": ["삭제하면 안 되는 05 데이터"]}},
    }


def contents(bundle):
    with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
        json_result = json.loads(zf.read("MASTER_ANALYSIS_merged.json"))
        hwpx_name = next(name for name in zf.namelist() if name.endswith(".hwpx"))
        hwpx = zf.read(hwpx_name)
    with zipfile.ZipFile(io.BytesIO(hwpx)) as zf:
        assert zf.testzip() is None
        section = etree.fromstring(zf.read("Contents/section0.xml"))
        header = etree.fromstring(zf.read("Contents/header.xml"))
        assert zf.infolist()[0].filename == "mimetype"
        assert zf.infolist()[0].compress_type == zipfile.ZIP_STORED
    return json_result, hwpx, section, header


def cell_paragraphs(cell):
    return ["".join(t.text or "" for t in p.findall(".//hp:t", HP))
            for p in cell.findall("./hp:subList/hp:p", HP)]


class MergerLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUTS.mkdir(exist_ok=True)

    def test_legacy_without_pronunciation(self):
        payload = {"PASSAGES": [sample_passage(1, False)]}
        bundle, _ = server.build_bundle(payload, "excluded")
        merged, hwpx, section, _ = contents(bundle)
        self.assertEqual(merged, payload)
        self.assertEqual(len(section.findall(".//hp:tbl", HP)), 6)
        self.assertNotIn("영작하기", "".join(section.itertext()))
        (OUTPUTS / "legacy_excluded.hwpx").write_bytes(hwpx)

    def test_both_options_identical_json_and_stacked_content(self):
        first = sample_passage(1, True, True)
        second = sample_passage(2, True)
        payload = {"PASSAGES": [first, second]}
        excluded_bundle, _ = server.build_bundle(payload, "excluded")
        included_bundle, _ = server.build_bundle(payload, "included")
        excluded, excluded_hwpx, excluded_section, excluded_header = contents(excluded_bundle)
        included, included_hwpx, included_section, header = contents(included_bundle)
        self.assertEqual(excluded, included)
        self.assertEqual(included, payload)
        self.assertEqual(len(included_section.findall(".//hp:tbl", HP)), 12)
        self.assertEqual(len(excluded_section.findall(".//hp:tbl", HP)), 12)
        self.assertNotIn("영작하기", "".join(included_section.itertext()))
        self.assertNotIn("영작하기", "".join(excluded_section.itertext()))
        self.assertIsNotNone(header.find(".//{http://www.hancom.co.kr/hwpml/2011/head}charPr[@id='30']"))
        tables = included_section.findall(".//hp:tbl", HP)
        for index, passage in enumerate(payload["PASSAGES"]):
            row = tables[index * 6 + 4].find("./hp:tr", HP)
            cells = row.findall("./hp:tc", HP)
            self.assertEqual(len(cells), 5)
            paragraphs = cell_paragraphs(cells[2])
            sentence = passage["지문"][0]
            expected = sentence["영어"].split("\n") + sentence["한글발음"].split("\n") + [""]
            self.assertEqual(paragraphs, expected)
            self.assertEqual(cell_paragraphs(cells[4]), sentence["한국어"].split("\n") + [""])
            pronunciation_run = cells[2].findall("./hp:subList/hp:p", HP)[len(sentence["영어"].split("\n"))].find("./hp:run", HP)
            self.assertEqual(pronunciation_run.get("charPrIDRef"), "31")
        self.assertIn("(even when progress is slow)", "".join(included_section.itertext()))
        normalized_included = copy.deepcopy(included_section)
        for index, passage in enumerate(payload["PASSAGES"]):
            rows = normalized_included.findall(".//hp:tbl", HP)[index * 6 + 4].findall("./hp:tr", HP)
            for row, sentence in zip(rows, passage["지문"]):
                sub = row.findall("./hp:tc", HP)[2].find("./hp:subList", HP)
                paragraphs = sub.findall("./hp:p", HP)
                start = len(sentence["영어"].split("\n"))
                count = len(sentence["한글발음"].split("\n"))
                for paragraph in paragraphs[start:start + count]:
                    sub.remove(paragraph)
        self.assertEqual(etree.tostring(excluded_section, method="c14n"),
                         etree.tostring(normalized_included, method="c14n"))

        normalized_header = copy.deepcopy(header)
        head_ns = "http://www.hancom.co.kr/hwpml/2011/head"
        for collection_name, style_name, style_id in (("charProperties", "charPr", "31"),
                                                      ("paraProperties", "paraPr", "26")):
            original = excluded_header.find(f".//{{{head_ns}}}{collection_name}")
            updated = normalized_header.find(f".//{{{head_ns}}}{collection_name}")
            updated.remove(updated.find(f"./{{{head_ns}}}{style_name}[@id='{style_id}']"))
            updated.set("itemCnt", original.get("itemCnt"))
        self.assertEqual(etree.tostring(excluded_header, method="c14n"),
                         etree.tostring(normalized_header, method="c14n"))
        with zipfile.ZipFile(io.BytesIO(excluded_hwpx)) as excluded_zip, zipfile.ZipFile(io.BytesIO(included_hwpx)) as included_zip:
            self.assertEqual(excluded_zip.namelist(), included_zip.namelist())
            for name in excluded_zip.namelist():
                if name not in ("Contents/section0.xml", "Contents/header.xml"):
                    self.assertEqual(excluded_zip.read(name), included_zip.read(name), name)
        (OUTPUTS / "sample_excluded.hwpx").write_bytes(excluded_hwpx)
        (OUTPUTS / "sample_included.hwpx").write_bytes(included_hwpx)
        (OUTPUTS / "sample_merged.json").write_text(json.dumps(included, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUTPUTS / "sample_excluded_bundle.zip").write_bytes(excluded_bundle)
        (OUTPUTS / "sample_included_bundle.zip").write_bytes(included_bundle)

    def test_validation_error_positions(self):
        for value, expected in ((None, "누락"), ("   ", "비어"), (42, "문자열"), ([], "문자열")):
            with self.subTest(value=value):
                payload = {"PASSAGES": [sample_passage(1, True), sample_passage(7, True)]}
                sentence = payload["PASSAGES"][1]["지문"][0]
                if value is None:
                    del sentence["한글발음"]
                else:
                    sentence["한글발음"] = value
                with self.assertRaisesRegex(ValueError, f"지문 7 · 문장 1.*{expected}"):
                    server.build_bundle(payload, "included")
                # The display option must not affect preservation/legacy compatibility.
                server.build_bundle(payload, "excluded")
        with self.assertRaises(ValueError):
            server.build_bundle({"PASSAGES": [sample_passage(1)]}, "unknown")
        empty = sample_passage(9)
        empty["지문"] = []
        with self.assertRaisesRegex(ValueError, "지문 9: 문장 배열이 비어"):
            server.build_bundle({"PASSAGES": [empty]}, "included")

    def test_multiple_sentences_keep_topic_emphasis(self):
        passage = sample_passage(4)
        second = {"한국어": "매일 계속하면 / 조금씩 성장한다.", "한글발음": "데일리 프랙티스 / 빌즈 어빌리티.",
                  "번호": "2", "영어": "Daily practice / builds ability."}
        passage["지문"].append(second)
        passage["주제문_번호"] = "2"
        bundle, _ = server.build_bundle({"PASSAGES": [passage]}, "included")
        _, _, section, _ = contents(bundle)
        rows = section.findall(".//hp:tbl", HP)[4].findall("./hp:tr", HP)
        self.assertEqual(len(rows), 2)
        self.assertEqual(cell_paragraphs(rows[1].findall("./hp:tc", HP)[2]),
                         [second["영어"], second["한글발음"], ""])
        self.assertEqual(cell_paragraphs(rows[1].findall("./hp:tc", HP)[4]), [second["한국어"], ""])
        number_run = rows[1].findall("./hp:tc", HP)[0].find(".//hp:run", HP)
        self.assertEqual(number_run.get("charPrIDRef"), "29")

    def test_edited_default_template_keeps_english_color_in_analysis(self):
        passage = sample_passage(1)
        passage["요지"] = "한국어 (English term) 그리고 (다른 뜻) 및 (second phrase)."
        bundle, _ = server.build_bundle({"PASSAGES": [passage]}, "excluded")
        _, _, section, header = contents(bundle)
        analysis = section.findall(".//hp:tbl", HP)[3]
        rows = analysis.findall("./hp:tr", HP)
        cell = rows[2].findall("./hp:tc", HP)[1]
        runs = cell.findall("./hp:subList/hp:p/hp:run", HP)
        self.assertEqual("".join("".join(t.text or "" for t in run.findall("./hp:t", HP)) for run in runs), passage["요지"])
        self.assertEqual([run.get("charPrIDRef") for run in runs], ["15", "30", "15", "30", "15"])
        blue = header.find(".//{http://www.hancom.co.kr/hwpml/2011/head}charPr[@id='30']")
        self.assertEqual(blue.get("textColor"), "#6182D6")
        title = rows[3].findall("./hp:tc", HP)[1]
        self.assertEqual([run.get("charPrIDRef") for run in title.findall("./hp:subList/hp:p/hp:run", HP)], ["15"])

    def test_html_defaults_to_excluded(self):
        html = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="pronunciation" value="excluded" checked', html)
        self.assertIn('name="pronunciation" value="included"', html)
        self.assertIn("pronunciation: document.querySelector", html)

    def test_http_route_option(self):
        httpd = server.ReusableServer(("127.0.0.1", 0), server.Handler)
        thread = Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/api/build-bundle"
            payload = {"mergedPayload": {"PASSAGES": [sample_passage(3, False)]}, "pronunciation": "included"}
            request = urllib.request.Request(url, json.dumps(payload, ensure_ascii=False).encode(), {"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request)
            self.assertIn("지문 3 · 문장 1", json.loads(raised.exception.read())["error"])
            payload["pronunciation"] = "excluded"
            request = urllib.request.Request(url, json.dumps(payload, ensure_ascii=False).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(contents(response.read())[0], payload["mergedPayload"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main(verbosity=2)
