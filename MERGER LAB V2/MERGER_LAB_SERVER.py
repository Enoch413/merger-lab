#!/usr/bin/env python3
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
import zipfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from logic_visualizer import validate_logic_visualization

HOST = "127.0.0.1"
PORT = 8782
ROOT_DIR = Path(__file__).resolve().parent
INDEX_PATH = ROOT_DIR / "index.html"
APP_INDEX_PATH = ROOT_DIR / "app" / "index.html"
GENERATOR_PATH = ROOT_DIR / "master_analysis_hwpx_generator.py"
LOGIC_VISUALIZER_PATH = ROOT_DIR / "logic_visualizer.py"
HWPX_EMBEDDER_PATH = ROOT_DIR / "hwpx_logic_embedder.py"
TEMPLATE_PATH = ROOT_DIR / "analysis_template.hwpx"
PRONUNCIATION_TEMPLATE_PATH = ROOT_DIR / "analysis_template_pronunciation.hwpx"

KEY_NUMBER = "\ubc88\ud638"
KEY_FULL_CONTENT = "\uc804\uccb4_\ub0b4\uc6a9"
KEY_BACKGROUND = "\ubc30\uacbd_\uc9c0\uc2dd"
KEY_MATERIAL = "\uc18c\uc7ac"
KEY_TOPIC = "\uc8fc\uc81c"
KEY_MAIN_IDEA = "\uc694\uc9c0"
KEY_TITLE = "\uc81c\ubaa9"
KEY_ONE_SENTENCE = "\ud55c_\ubb38\uc7a5_\uc694\uc57d"
KEY_TOPIC_SENTENCE = "\uc8fc\uc81c\ubb38_\ubc88\ud638"
KEY_SENTENCES = "\uc9c0\ubb38"
KEY_PRONUNCIATION = "\ud55c\uae00\ubc1c\uc74c"
KEY_VOCAB = "\uc5b4\ud718"
KEY_POINTS = "\ucd9c\uc81c\ud3ec\uc778\ud2b8"
REQUIRED_KEYS = [KEY_NUMBER, KEY_FULL_CONTENT, KEY_BACKGROUND, KEY_MATERIAL, KEY_TOPIC, KEY_MAIN_IDEA, KEY_TITLE, KEY_ONE_SENTENCE, KEY_TOPIC_SENTENCE, KEY_SENTENCES, KEY_VOCAB, KEY_POINTS]
MAX_HEADER_TEXT_LENGTH = 40

class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def validate_header_text(value, label):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label}은 문자열이어야 합니다.")
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise ValueError(f"{label}에는 줄바꿈을 넣을 수 없습니다.")
    if len(value) > MAX_HEADER_TEXT_LENGTH:
        raise ValueError(f"{label}은 {MAX_HEADER_TEXT_LENGTH}자 이하여야 합니다.")
    return value


def build_range_map(passages, range_text="", range_rules=None):
    range_text = validate_header_text(range_text, "범위")
    if range_rules is None:
        range_rules = []
    if not isinstance(range_rules, list):
        raise ValueError("범위 구간은 배열이어야 합니다.")
    if not range_rules:
        return [range_text] * len(passages)

    passage_numbers = []
    for index, passage in enumerate(passages):
        number = passage.get(KEY_NUMBER) if isinstance(passage, dict) else None
        if isinstance(number, bool) or not str(number).strip().isdigit():
            raise ValueError(f"범위 구간을 사용하려면 지문 {index + 1}의 번호가 양의 정수여야 합니다.")
        passage_numbers.append(int(str(number).strip()))

    range_map = [range_text] * len(passages)
    assigned = [False] * len(passages)
    first_number, last_number = min(passage_numbers), max(passage_numbers)
    expected_keys = {"start", "end", "text"}
    for rule_index, rule in enumerate(range_rules, start=1):
        location = f"범위 구간 {rule_index}"
        if not isinstance(rule, dict):
            raise ValueError(f"{location}은 객체여야 합니다.")
        if set(rule) != expected_keys:
            raise ValueError(f"{location}에는 start, end, text만 있어야 합니다.")
        start, end = rule["start"], rule["end"]
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            raise ValueError(f"{location}의 시작·끝 지문 번호는 정수여야 합니다.")
        if start < 1 or end < 1:
            raise ValueError(f"{location}의 지문 번호는 1 이상이어야 합니다.")
        if start > end:
            raise ValueError(f"{location}의 시작 번호는 끝 번호보다 클 수 없습니다.")
        if start < first_number or end > last_number:
            raise ValueError(f"{location}의 지문 번호는 {first_number}~{last_number} 안에 있어야 합니다.")
        text = validate_header_text(rule["text"], location)
        if not text:
            raise ValueError(f"{location}의 표시 문구가 비어 있습니다.")

        matched = False
        for passage_index, passage_number in enumerate(passage_numbers):
            if start <= passage_number <= end:
                matched = True
                if assigned[passage_index]:
                    raise ValueError(f"범위 구간이 겹칩니다: 지문 {passage_number}")
                assigned[passage_index] = True
                range_map[passage_index] = text
        if not matched:
            raise ValueError(f"{location}에 해당하는 지문이 없습니다: {start}~{end}")

    if range_rules and not range_text:
        missing = [str(number) for number, used in zip(passage_numbers, assigned) if not used]
        if missing:
            raise ValueError(f"범위가 지정되지 않은 지문이 있습니다: {', '.join(missing)}")
    return range_map


def validate_payload(payload, pronunciation="excluded", output_mode="compatibility"):
    if pronunciation not in ("excluded", "included"):
        raise ValueError("발음 옵션은 'included' 또는 'excluded'여야 합니다.")
    if output_mode not in ("compatibility", "v2"):
        raise ValueError("출력 모드는 'compatibility' 또는 'v2'여야 합니다.")
    if not isinstance(payload, dict):
        raise ValueError("Root payload must be a JSON object.")
    passages = payload.get("PASSAGES")
    if not isinstance(passages, list) or not passages:
        raise ValueError("PASSAGES must be a non-empty array.")
    for index, passage in enumerate(passages):
        if not isinstance(passage, dict):
            raise ValueError(f"PASSAGES[{index}] must be an object.")
        missing = [key for key in REQUIRED_KEYS if key not in passage]
        if missing:
            raise ValueError(f"PASSAGES[{index}] is missing required keys: {', '.join(missing)}")
        if not isinstance(passage.get(KEY_POINTS), dict):
            raise ValueError(f"PASSAGES[{index}].{KEY_POINTS} must be an object.")
        if pronunciation == "included":
            sentences = passage.get(KEY_SENTENCES)
            if not isinstance(sentences, list):
                raise ValueError(f"지문 {passage.get(KEY_NUMBER, index + 1)}의 지문 배열이 올바르지 않습니다.")
            if not sentences:
                raise ValueError(f"지문 {passage.get(KEY_NUMBER, index + 1)}: 문장 배열이 비어 있습니다.")
            for sentence_index, sentence in enumerate(sentences):
                number = sentence.get(KEY_NUMBER, sentence_index + 1) if isinstance(sentence, dict) else sentence_index + 1
                location = f"지문 {passage.get(KEY_NUMBER, index + 1)} · 문장 {number}"
                if not isinstance(sentence, dict) or KEY_PRONUNCIATION not in sentence:
                    raise ValueError(f"{location}: 한글발음이 누락되었습니다.")
                value = sentence[KEY_PRONUNCIATION]
                if not isinstance(value, str):
                    raise ValueError(f"{location}: 한글발음은 문자열이어야 합니다 (현재 {type(value).__name__}).")
                if not value.strip():
                    raise ValueError(f"{location}: 한글발음이 비어 있습니다.")
        if output_mode == "v2":
            validate_logic_visualization(passage, index)


def decode_process_output(raw):
    if not raw:
        return ""
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def find_generated_hwpx(workdir: Path) -> Path:
    candidates = [path for path in workdir.glob("분석결과_*.hwpx") if path.is_file()]
    if not candidates:
        raise FileNotFoundError("Generated HWPX file was not found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_bundle(payload, pronunciation="excluded", output_mode="compatibility", school="", range_text="", range_rules=None):
    validate_payload(payload, pronunciation, output_mode)
    school = validate_header_text(school, "학교")
    range_map = build_range_map(payload["PASSAGES"], range_text, range_rules)
    template_path = PRONUNCIATION_TEMPLATE_PATH if pronunciation == "included" else TEMPLATE_PATH
    with tempfile.TemporaryDirectory(prefix="merger_lab_") as temp_dir:
        workdir = Path(temp_dir)
        merged_bytes = json_bytes(payload)
        (workdir / "MASTER_ANALYSIS_merged.json").write_bytes(merged_bytes)
        (workdir / "input.json").write_bytes(merged_bytes)
        (workdir / "range_map.json").write_bytes(json_bytes(range_map))
        shutil.copy2(template_path, workdir / template_path.name)
        shutil.copy2(GENERATOR_PATH, workdir / GENERATOR_PATH.name)
        shutil.copy2(LOGIC_VISUALIZER_PATH, workdir / LOGIC_VISUALIZER_PATH.name)
        shutil.copy2(HWPX_EMBEDDER_PATH, workdir / HWPX_EMBEDDER_PATH.name)
        completed = subprocess.run(
            [sys.executable, str(workdir / GENERATOR_PATH.name), "--template", template_path.name,
             "--pronunciation", pronunciation, "--mode", output_mode,
             "--school", school, "--range-map-file", "range_map.json"], cwd=workdir, capture_output=True
        )
        if completed.returncode != 0:
            stderr = decode_process_output(completed.stderr)
            stdout = decode_process_output(completed.stdout)
            raise RuntimeError((stderr or stdout or "HWPX generation failed.").strip())
        hwpx_path = find_generated_hwpx(workdir)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_name = f"MASTER_ANALYSIS_bundle_{stamp}.zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("MASTER_ANALYSIS_merged.json", merged_bytes)
            zf.write(hwpx_path, hwpx_path.name)
            for diagram in sorted((workdir / "diagrams").glob("*.png")) if (workdir / "diagrams").exists() else []:
                zf.write(diagram, f"diagrams/{diagram.name}")
        return buffer.getvalue(), download_name


class Handler(BaseHTTPRequestHandler):
    server_version = "MergerLab/2.0"

    def log_message(self, format, *args):
        return

    def send_utf8(self, status, body, content_type):
        body_bytes = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def send_json(self, status, payload):
        self.send_utf8(status, json.dumps(payload, ensure_ascii=False), "application/json")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            if INDEX_PATH.exists():
                self.send_utf8(HTTPStatus.OK, INDEX_PATH.read_text(encoding="utf-8"), "text/html")
                return
            if APP_INDEX_PATH.exists():
                self.send_utf8(HTTPStatus.OK, APP_INDEX_PATH.read_text(encoding="utf-8"), "text/html")
                return
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "index.html was not found."})
            return
        if path in ("/app/", "/app/index.html"):
            if APP_INDEX_PATH.exists():
                self.send_utf8(HTTPStatus.OK, APP_INDEX_PATH.read_text(encoding="utf-8"), "text/html")
                return
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "app/index.html was not found."})
            return
        if path == "/api/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "version": "2.0", "modes": ["compatibility", "v2"]})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Route not found."})

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/api/build-bundle":
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Route not found."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            request_payload = json.loads(raw.decode("utf-8"))
            bundle_bytes, download_name = build_bundle(
                request_payload.get("mergedPayload"),
                request_payload.get("pronunciation", "excluded"),
                request_payload.get("outputMode", "compatibility"),
                request_payload.get("school", ""),
                request_payload.get("range", ""),
                request_payload.get("rangeRules"),
            )
        except json.JSONDecodeError:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Request body is not valid JSON."})
            return
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return
        quoted = urllib.parse.quote(download_name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(bundle_bytes)))
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
        self.end_headers()
        self.wfile.write(bundle_bytes)


def ensure_assets():
    for path in (
        GENERATOR_PATH,
        LOGIC_VISUALIZER_PATH,
        HWPX_EMBEDDER_PATH,
        TEMPLATE_PATH,
        PRONUNCIATION_TEMPLATE_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")


def main():
    ensure_assets()
    url = f"http://{HOST}:{PORT}/"
    server = ReusableServer((HOST, PORT), Handler)
    threading.Timer(0.6, lambda: webbrowser.open_new_tab(url)).start()
    print(f"MERGER LAB running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
