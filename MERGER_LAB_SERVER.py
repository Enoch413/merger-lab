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

HOST = "127.0.0.1"
PORT = 8781
ROOT_DIR = Path(__file__).resolve().parent
INDEX_PATH = ROOT_DIR / "index.html"
APP_INDEX_PATH = ROOT_DIR / "app" / "index.html"
GENERATOR_PATH = ROOT_DIR / "master_analysis_hwpx_generator.py"
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

class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def validate_payload(payload, pronunciation="excluded"):
    if pronunciation not in ("excluded", "included"):
        raise ValueError("발음 옵션은 'included' 또는 'excluded'여야 합니다.")
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


def build_bundle(payload, pronunciation="excluded"):
    validate_payload(payload, pronunciation)
    template_path = PRONUNCIATION_TEMPLATE_PATH if pronunciation == "included" else TEMPLATE_PATH
    with tempfile.TemporaryDirectory(prefix="merger_lab_") as temp_dir:
        workdir = Path(temp_dir)
        merged_bytes = json_bytes(payload)
        (workdir / "MASTER_ANALYSIS_merged.json").write_bytes(merged_bytes)
        (workdir / "input.json").write_bytes(merged_bytes)
        shutil.copy2(template_path, workdir / template_path.name)
        shutil.copy2(GENERATOR_PATH, workdir / GENERATOR_PATH.name)
        completed = subprocess.run(
            [sys.executable, str(workdir / GENERATOR_PATH.name), "--template", template_path.name,
             "--pronunciation", pronunciation], cwd=workdir, capture_output=True
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
        return buffer.getvalue(), download_name


class Handler(BaseHTTPRequestHandler):
    server_version = "MergerLab/1.0"

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
            self.send_json(HTTPStatus.OK, {"ok": True})
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
                request_payload.get("mergedPayload"), request_payload.get("pronunciation", "excluded")
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
    for path in (GENERATOR_PATH, TEMPLATE_PATH, PRONUNCIATION_TEMPLATE_PATH):
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
