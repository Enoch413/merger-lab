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
HTML = '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>MASTER ANALYSIS BUNDLE</title>\n<style>\n  :root{\n    --bg:#eef4f1;\n    --surface:#ffffff;\n    --surface-soft:#f7fbf9;\n    --border:#cfe0d9;\n    --border-strong:#9ec0b5;\n    --ink:#173631;\n    --muted:#5f7871;\n    --accent:#0f6a5b;\n    --accent-strong:#0b5448;\n    --accent-soft:#dff1eb;\n    --danger:#b5473f;\n    --shadow:0 22px 48px rgba(22, 54, 49, 0.12);\n  }\n\n  *{box-sizing:border-box}\n  html,body{margin:0;padding:0}\n  body{\n    min-height:100vh;\n    font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;\n    color:var(--ink);\n    background:\n      radial-gradient(circle at top left, rgba(15,106,91,.12), transparent 28%),\n      linear-gradient(180deg, #f7fbf9 0%, #edf4f1 100%);\n  }\n\n  .page{\n    width:min(1120px, calc(100% - 32px));\n    margin:32px auto 48px;\n  }\n\n  .hero{\n    padding:28px 30px;\n    border:1px solid var(--border);\n    border-radius:28px;\n    background:rgba(255,255,255,.86);\n    box-shadow:var(--shadow);\n    backdrop-filter:blur(10px);\n  }\n\n  .eyebrow{\n    font-size:12px;\n    font-weight:800;\n    letter-spacing:.14em;\n    color:var(--accent);\n    text-transform:uppercase;\n  }\n\n  h1{\n    margin:10px 0 8px;\n    font-size:clamp(30px, 4vw, 48px);\n    line-height:1;\n    letter-spacing:-.03em;\n  }\n\n  .hero p{\n    margin:0;\n    max-width:760px;\n    color:var(--muted);\n    font-size:15px;\n    line-height:1.75;\n  }\n\n  .hero-notes{\n    display:grid;\n    grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));\n    gap:12px;\n    margin-top:20px;\n  }\n\n  .note{\n    padding:14px 16px;\n    border:1px solid var(--border);\n    border-radius:18px;\n    background:var(--surface-soft);\n    font-size:14px;\n    line-height:1.7;\n    color:var(--ink);\n  }\n\n  .layout{\n    display:grid;\n    grid-template-columns:minmax(360px, 1.05fr) minmax(360px, .95fr);\n    gap:20px;\n    margin-top:20px;\n  }\n\n  .panel{\n    border:1px solid var(--border);\n    border-radius:26px;\n    background:rgba(255,255,255,.92);\n    box-shadow:var(--shadow);\n    overflow:hidden;\n  }\n\n  .panel-head{\n    display:flex;\n    justify-content:space-between;\n    align-items:flex-end;\n    gap:12px;\n    padding:22px 24px 16px;\n    border-bottom:1px solid var(--border);\n    background:linear-gradient(180deg, rgba(223,241,235,.55) 0%, rgba(255,255,255,0) 100%);\n  }\n\n  .panel-title{\n    font-size:24px;\n    font-weight:800;\n    letter-spacing:-.03em;\n  }\n\n  .panel-sub{\n    margin-top:6px;\n    color:var(--muted);\n    font-size:13px;\n    line-height:1.65;\n  }\n\n  .panel-body{\n    padding:20px 24px 24px;\n  }\n\n  .drop-zone{\n    position:relative;\n    display:flex;\n    flex-direction:column;\n    justify-content:center;\n    align-items:center;\n    min-height:180px;\n    padding:24px;\n    border:2px dashed var(--border-strong);\n    border-radius:22px;\n    background:linear-gradient(180deg, rgba(223,241,235,.68) 0%, rgba(247,251,249,1) 100%);\n    text-align:center;\n    transition:border-color .18s ease, transform .18s ease, background .18s ease;\n  }\n\n  .drop-zone.dragover{\n    border-color:var(--accent);\n    background:linear-gradient(180deg, rgba(193,232,222,.92) 0%, rgba(243,250,247,1) 100%);\n    transform:translateY(-1px);\n  }\n\n  .drop-zone input{\n    position:absolute;\n    inset:0;\n    opacity:0;\n    cursor:pointer;\n  }\n\n  .drop-icon{\n    width:62px;\n    height:62px;\n    display:grid;\n    place-items:center;\n    margin-bottom:12px;\n    border-radius:20px;\n    background:rgba(15,106,91,.12);\n    font-size:30px;\n  }\n\n  .drop-title{\n    font-size:20px;\n    font-weight:800;\n  }\n\n  .drop-sub{\n    margin-top:8px;\n    max-width:360px;\n    color:var(--muted);\n    font-size:14px;\n    line-height:1.7;\n  }\n\n  .controls{\n    display:flex;\n    flex-wrap:wrap;\n    gap:12px;\n    align-items:flex-end;\n    margin-top:18px;\n  }\n\n  .field{\n    display:flex;\n    flex-direction:column;\n    gap:6px;\n  }\n\n  .field label{\n    font-size:12px;\n    font-weight:700;\n    color:var(--muted);\n    letter-spacing:.04em;\n    text-transform:uppercase;\n  }\n\n  .field input{\n    width:120px;\n    padding:12px 14px;\n    border:1px solid var(--border);\n    border-radius:14px;\n    background:#fff;\n    font-size:15px;\n    color:var(--ink);\n  }\n\n  .button-row{\n    display:flex;\n    flex-wrap:wrap;\n    gap:10px;\n  }\n\n  button{\n    border:none;\n    border-radius:14px;\n    padding:12px 16px;\n    font-size:14px;\n    font-weight:800;\n    cursor:pointer;\n    transition:transform .15s ease, opacity .15s ease, background .15s ease;\n  }\n\n  button:active{transform:scale(.98)}\n  button:disabled{opacity:.45;cursor:not-allowed}\n\n  .btn-primary{background:var(--accent);color:#fff}\n  .btn-primary:hover{background:var(--accent-strong)}\n  .btn-secondary{background:var(--accent-soft);color:var(--accent-strong)}\n  .btn-ghost{background:#fff;border:1px solid var(--border);color:var(--ink)}\n  .btn-danger{background:#fff4f3;border:1px solid rgba(181,71,63,.22);color:var(--danger)}\n  .btn-mini{\n    padding:8px 10px;\n    font-size:12px;\n    border-radius:10px;\n  }\n\n  .summary{\n    display:grid;\n    grid-template-columns:repeat(3, minmax(0, 1fr));\n    gap:10px;\n    margin-top:18px;\n  }\n\n  .summary-card{\n    padding:14px 16px;\n    border:1px solid var(--border);\n    border-radius:18px;\n    background:var(--surface-soft);\n  }\n\n  .summary-label{\n    font-size:12px;\n    color:var(--muted);\n    text-transform:uppercase;\n    letter-spacing:.06em;\n    font-weight:700;\n  }\n\n  .summary-value{\n    margin-top:4px;\n    font-size:26px;\n    font-weight:800;\n    letter-spacing:-.03em;\n  }\n\n  .file-list{\n    display:flex;\n    flex-direction:column;\n    gap:12px;\n    margin-top:20px;\n  }\n\n  .file-card{\n    display:grid;\n    grid-template-columns:auto minmax(0, 1fr) auto;\n    gap:14px;\n    align-items:center;\n    padding:14px 16px;\n    border:1px solid var(--border);\n    border-radius:18px;\n    background:#fff;\n  }\n\n  .file-order{\n    width:42px;\n    height:42px;\n    display:grid;\n    place-items:center;\n    border-radius:14px;\n    background:var(--accent-soft);\n    color:var(--accent-strong);\n    font-size:17px;\n    font-weight:800;\n  }\n\n  .file-name{\n    font-size:15px;\n    font-weight:800;\n    line-height:1.45;\n    word-break:break-all;\n  }\n\n  .file-meta{\n    margin-top:4px;\n    color:var(--muted);\n    font-size:13px;\n    line-height:1.6;\n  }\n\n  .file-actions{\n    display:flex;\n    flex-wrap:wrap;\n    gap:8px;\n    justify-content:flex-end;\n  }\n\n  .status{\n    margin-top:16px;\n    padding:14px 16px;\n    border-radius:18px;\n    border:1px solid var(--border);\n    background:var(--surface-soft);\n    font-size:14px;\n    line-height:1.7;\n    color:var(--ink);\n  }\n\n  .status.warn{\n    border-color:rgba(181,71,63,.28);\n    background:#fff4f3;\n    color:#7c2e29;\n  }\n\n  .status.ok{\n    border-color:rgba(15,106,91,.22);\n    background:rgba(223,241,235,.7);\n    color:var(--accent-strong);\n  }\n\n  .preview-box{\n    min-height:420px;\n    padding:16px;\n    border:1px solid var(--border);\n    border-radius:20px;\n    background:#0d1614;\n    color:#def4ec;\n    overflow:auto;\n  }\n\n  pre{\n    margin:0;\n    white-space:pre-wrap;\n    word-break:break-word;\n    font-size:13px;\n    line-height:1.7;\n    font-family:"JetBrains Mono","Fira Code","Consolas",monospace;\n  }\n\n  .empty{\n    display:grid;\n    place-items:center;\n    min-height:220px;\n    padding:24px;\n    border:1px dashed var(--border);\n    border-radius:20px;\n    color:var(--muted);\n    text-align:center;\n    line-height:1.8;\n    background:var(--surface-soft);\n  }\n\n  .tip-list{\n    margin:14px 0 0;\n    padding-left:18px;\n    color:var(--muted);\n    font-size:13px;\n    line-height:1.8;\n  }\n\n  .preview-switch{\n    display:flex;\n    flex-wrap:wrap;\n    gap:10px;\n    margin-bottom:12px;\n  }\n\n  @media (max-width: 940px){\n    .layout{grid-template-columns:1fr}\n  }\n\n  @media (max-width: 640px){\n    .page{width:min(100% - 20px, 100%)}\n    .hero,.panel-body,.panel-head{padding-left:18px;padding-right:18px}\n    .summary{grid-template-columns:1fr}\n    .file-card{grid-template-columns:1fr}\n    .file-actions{justify-content:flex-start}\n  }\n</style>\n</head>\n<body>\n  <main class="page">\n    <section class="hero">\n      <div class="eyebrow">CodeLab Tool</div>\n      <h1>MASTER ANALYSIS BUNDLE</h1>\n      <p>한 지문씩 받은 <code>MASTER_ANALYSIS.json</code> 파일들을 업로드하면, 업로드 순서대로 <code>PASSAGES[*].번호</code>를 다시 매기고 전체 통합본, 05-only 통합본, HWPX 결과물을 한 번에 묶어 내려받을 수 있습니다. 기본 <code>분석_템플릿.hwpx</code>는 도구 안에 포함되어 있어 매번 업로드할 필요가 없습니다.</p>\n      <div class="hero-notes">\n        <div class="note"><strong>번호 재부여 기준</strong><br>업로드 순서대로 1, 2, 3... 순번을 다시 부여합니다. 필요하면 업로드 후 순서를 위/아래로 바꿀 수 있습니다.</div>\n        <div class="note"><strong>변경되는 값</strong><br><code>PASSAGES[*].번호</code>만 순서 기준으로 다시 씁니다. 문장 번호나 다른 내용은 그대로 유지합니다.</div>\n        <div class="note"><strong>최종 ZIP 1개</strong><br><code>MASTER_ANALYSIS_merged.json</code>, <code>MASTER_ANALYSIS_05_only_merged.json</code>, 생성된 HWPX 파일을 ZIP 하나로 함께 내려받습니다.</div>\n      </div>\n    </section>\n\n    <section class="layout">\n      <div class="panel">\n        <div class="panel-head">\n          <div>\n            <div class="panel-title">파일 업로드</div>\n            <div class="panel-sub">JSON 파일을 여러 개 올린 뒤 순서를 확인하고, 필요하면 위아래로 조정하세요.</div>\n          </div>\n        </div>\n        <div class="panel-body">\n          <label class="drop-zone" id="drop-zone">\n            <input type="file" id="file-input" accept=".json,application/json" multiple>\n            <div class="drop-icon">+</div>\n            <div class="drop-title">JSON 파일 추가</div>\n            <div class="drop-sub">여러 개를 한 번에 올려도 됩니다. 드래그 앤 드롭도 지원합니다.</div>\n          </label>\n\n          <div class="controls">\n            <div class="field">\n              <label for="start-number">시작 번호</label>\n              <input id="start-number" type="number" min="1" step="1" value="1">\n            </div>\n            <div class="button-row">\n              <button class="btn-secondary" id="clear-btn" type="button">전체 비우기</button>\n              <button class="btn-primary" id="bundle-btn" type="button" disabled>ZIP 3종 다운로드</button>\n            </div>\n          </div>\n\n          <div class="summary">\n            <div class="summary-card">\n              <div class="summary-label">업로드 파일</div>\n              <div class="summary-value" id="file-count">0</div>\n            </div>\n            <div class="summary-card">\n              <div class="summary-label">통합 Passage</div>\n              <div class="summary-value" id="passage-count">0</div>\n            </div>\n            <div class="summary-card">\n              <div class="summary-label">다음 번호</div>\n              <div class="summary-value" id="next-number">1</div>\n            </div>\n          </div>\n\n          <div class="status" id="status-box">아직 업로드된 파일이 없습니다.</div>\n          <div class="file-list" id="file-list"></div>\n        </div>\n      </div>\n\n      <div class="panel">\n        <div class="panel-head">\n          <div>\n            <div class="panel-title">통합 미리보기</div>\n            <div class="panel-sub">전체 통합본과 05-only 통합본을 번갈아 보면서 번호와 구조를 바로 확인할 수 있습니다.</div>\n          </div>\n        </div>\n        <div class="panel-body">\n          <div class="preview-switch">\n            <button class="btn-primary" id="preview-full-btn" type="button">전체 통합본</button>\n            <button class="btn-ghost" id="preview-05-btn" type="button">05 only 통합본</button>\n          </div>\n          <div class="preview-box">\n            <pre id="preview-text">{\n  "PASSAGES": []\n}</pre>\n          </div>\n          <ul class="tip-list">\n            <li>업로드 순서가 곧 passage 번호 순서입니다.</li>\n            <li><code>PASSAGES[*].번호</code>만 다시 씁니다.</li>\n            <li><code>05 only</code> 통합본은 각 passage의 <code>번호</code>와 <code>출제포인트</code>만 남깁니다.</li>\n            <li>ZIP 생성은 로컬 서버 모드에서 동작합니다. <code>tools/master_analysis_bundle/START_MASTER_ANALYSIS_BUNDLE.bat</code>로 여는 것을 권장합니다.</li>\n            <li>원본 JSON 파일은 수정되지 않습니다.</li>\n          </ul>\n        </div>\n      </div>\n    </section>\n  </main>\n\n<script>\n(() => {\n  const state = {\n    items: [],\n    previewMode: "full"\n  };\n\n  const fileInput = document.getElementById("file-input");\n  const dropZone = document.getElementById("drop-zone");\n  const startNumberInput = document.getElementById("start-number");\n  const clearBtn = document.getElementById("clear-btn");\n  const bundleBtn = document.getElementById("bundle-btn");\n  const fileList = document.getElementById("file-list");\n  const fileCount = document.getElementById("file-count");\n  const passageCount = document.getElementById("passage-count");\n  const nextNumber = document.getElementById("next-number");\n  const statusBox = document.getElementById("status-box");\n  const previewText = document.getElementById("preview-text");\n  const previewFullBtn = document.getElementById("preview-full-btn");\n  const preview05Btn = document.getElementById("preview-05-btn");\n\n  const formatPassageRange = (start, count) => {\n    if (count <= 0) return "-";\n    if (count === 1) return String(start);\n    return start + " ~ " + (start + count - 1);\n  };\n\n  const deepClone = (value) => JSON.parse(JSON.stringify(value));\n\n  const getStartNumber = () => {\n    const parsed = Number.parseInt(startNumberInput.value, 10);\n    if (!Number.isFinite(parsed) || parsed < 1) return 1;\n    return parsed;\n  };\n\n  const extractPassages = (payload, fileName) => {\n    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {\n      throw new Error(fileName + ": JSON 최상위는 객체여야 합니다.");\n    }\n    if (!Array.isArray(payload.PASSAGES)) {\n      throw new Error(fileName + ": `PASSAGES` 배열이 없습니다.");\n    }\n    if (payload.PASSAGES.length === 0) {\n      throw new Error(fileName + ": `PASSAGES` 배열이 비어 있습니다.");\n    }\n\n    payload.PASSAGES.forEach((passage, index) => {\n      if (!passage || typeof passage !== "object" || Array.isArray(passage)) {\n        throw new Error(fileName + ": PASSAGES[" + index + "]가 객체가 아닙니다.");\n      }\n      if (!("출제포인트" in passage) || !passage.출제포인트 || typeof passage.출제포인트 !== "object" || Array.isArray(passage.출제포인트)) {\n        throw new Error(fileName + ": PASSAGES[" + index + "]에 `출제포인트` 객체가 없습니다.");\n      }\n    });\n\n    return payload.PASSAGES;\n  };\n\n  const buildMergedPayload = () => {\n    const startNumber = getStartNumber();\n    let currentNumber = startNumber;\n    const merged = { PASSAGES: [] };\n\n    state.items.forEach((item) => {\n      item.passages.forEach((passage) => {\n        const nextPassage = deepClone(passage);\n        nextPassage.번호 = String(currentNumber);\n        merged.PASSAGES.push(nextPassage);\n        currentNumber += 1;\n      });\n    });\n\n    return merged;\n  };\n\n  const buildMerged05Payload = () => {\n    const merged = buildMergedPayload();\n    return {\n      PASSAGES: merged.PASSAGES.map((passage) => ({\n        번호: String(passage.번호),\n        출제포인트: deepClone(passage.출제포인트 || {})\n      }))\n    };\n  };\n\n  const getPreviewPayload = () => {\n    return state.previewMode === "05" ? buildMerged05Payload() : buildMergedPayload();\n  };\n\n  const updateSummary = () => {\n    const startNumber = getStartNumber();\n    const totalFiles = state.items.length;\n    const totalPassages = state.items.reduce((sum, item) => sum + item.passages.length, 0);\n\n    fileCount.textContent = String(totalFiles);\n    passageCount.textContent = String(totalPassages);\n    nextNumber.textContent = String(startNumber + totalPassages);\n  };\n\n  const updateStatus = (message, type = "") => {\n    statusBox.textContent = message;\n    statusBox.className = "status" + (type ? " " + type : "");\n  };\n\n  const renderList = () => {\n    fileList.innerHTML = "";\n\n    if (!state.items.length) {\n      const empty = document.createElement("div");\n      empty.className = "empty";\n      empty.textContent = "업로드된 JSON 파일이 없습니다. 위 영역에 파일을 올리면 여기서 순서를 확인할 수 있습니다.";\n      fileList.appendChild(empty);\n      return;\n    }\n\n    let runningNumber = getStartNumber();\n\n    state.items.forEach((item, index) => {\n      const card = document.createElement("div");\n      card.className = "file-card";\n\n      const order = document.createElement("div");\n      order.className = "file-order";\n      order.textContent = String(index + 1);\n\n      const body = document.createElement("div");\n      const name = document.createElement("div");\n      name.className = "file-name";\n      name.textContent = item.fileName;\n\n      const meta = document.createElement("div");\n      meta.className = "file-meta";\n      meta.textContent =\n        "passage " + item.passages.length + "개 | 새 번호 " +\n        formatPassageRange(runningNumber, item.passages.length);\n\n      runningNumber += item.passages.length;\n      body.append(name, meta);\n\n      const actions = document.createElement("div");\n      actions.className = "file-actions";\n\n      const upBtn = document.createElement("button");\n      upBtn.className = "btn-ghost btn-mini";\n      upBtn.type = "button";\n      upBtn.textContent = "위로";\n      upBtn.disabled = index === 0;\n      upBtn.addEventListener("click", () => moveItem(index, -1));\n\n      const downBtn = document.createElement("button");\n      downBtn.className = "btn-ghost btn-mini";\n      downBtn.type = "button";\n      downBtn.textContent = "아래로";\n      downBtn.disabled = index === state.items.length - 1;\n      downBtn.addEventListener("click", () => moveItem(index, 1));\n\n      const removeBtn = document.createElement("button");\n      removeBtn.className = "btn-danger btn-mini";\n      removeBtn.type = "button";\n      removeBtn.textContent = "삭제";\n      removeBtn.addEventListener("click", () => removeItem(index));\n\n      actions.append(upBtn, downBtn, removeBtn);\n      card.append(order, body, actions);\n      fileList.appendChild(card);\n    });\n  };\n\n  const updatePreview = () => {\n    const merged = buildMergedPayload();\n    previewText.textContent = JSON.stringify(getPreviewPayload(), null, 2);\n\n    const hasItems = merged.PASSAGES.length > 0;\n    bundleBtn.disabled = !hasItems;\n    previewFullBtn.className = state.previewMode === "full" ? "btn-primary" : "btn-ghost";\n    preview05Btn.className = state.previewMode === "05" ? "btn-primary" : "btn-ghost";\n\n    if (!hasItems) {\n      updateStatus("아직 업로드된 파일이 없습니다.");\n      return;\n    }\n\n    updateStatus(\n      "총 " + merged.PASSAGES.length + "개 passage가 통합되었습니다. 서버 모드에서 ZIP 1개로 전체 JSON, 05-only JSON, HWPX를 함께 받을 수 있습니다.",\n      "ok"\n    );\n  };\n\n  const refresh = () => {\n    updateSummary();\n    renderList();\n    updatePreview();\n  };\n\n  const moveItem = (index, offset) => {\n    const targetIndex = index + offset;\n    if (targetIndex < 0 || targetIndex >= state.items.length) return;\n    const [moved] = state.items.splice(index, 1);\n    state.items.splice(targetIndex, 0, moved);\n    refresh();\n  };\n\n  const removeItem = (index) => {\n    state.items.splice(index, 1);\n    refresh();\n  };\n\n  const addFiles = async (files) => {\n    const incoming = Array.from(files || []);\n    if (!incoming.length) return;\n\n    for (const file of incoming) {\n      try {\n        const raw = await file.text();\n        const payload = JSON.parse(raw);\n        const passages = extractPassages(payload, file.name).map((passage) => deepClone(passage));\n        state.items.push({\n          id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()),\n          fileName: file.name,\n          passages\n        });\n      } catch (error) {\n        updateStatus(error.message || (file.name + ": JSON을 읽는 중 오류가 발생했습니다."), "warn");\n      }\n    }\n\n    fileInput.value = "";\n    refresh();\n  };\n\n  const downloadBlob = (blob, fileName) => {\n    const url = URL.createObjectURL(blob);\n    const anchor = document.createElement("a");\n    anchor.href = url;\n    anchor.download = fileName;\n    document.body.appendChild(anchor);\n    anchor.click();\n    anchor.remove();\n    URL.revokeObjectURL(url);\n  };\n\n  const parseDownloadName = (contentDisposition) => {\n    if (!contentDisposition) return "MASTER_ANALYSIS_bundle.zip";\n    const utfMatch = contentDisposition.match(/filename\\*=UTF-8\'\'([^;]+)/i);\n    if (utfMatch && utfMatch[1]) {\n      return decodeURIComponent(utfMatch[1]);\n    }\n    const plainMatch = contentDisposition.match(/filename=\\"?([^\\";]+)\\"?/i);\n    if (plainMatch && plainMatch[1]) {\n      return plainMatch[1];\n    }\n    return "MASTER_ANALYSIS_bundle.zip";\n  };\n\n  const downloadBundle = async () => {\n    if (!state.items.length) return;\n\n    if (window.location.protocol === "file:") {\n      updateStatus("ZIP 생성은 파일 직접 열기 모드에서는 동작하지 않습니다. `tools/master_analysis_bundle/START_MASTER_ANALYSIS_BUNDLE.bat`로 열어 주세요.", "warn");\n      return;\n    }\n\n    const originalLabel = bundleBtn.textContent;\n    bundleBtn.disabled = true;\n    bundleBtn.textContent = "ZIP 생성 중...";\n\n    try {\n      const response = await fetch("/api/build-bundle", {\n        method: "POST",\n        headers: {\n          "Content-Type": "application/json"\n        },\n        body: JSON.stringify({\n          mergedPayload: buildMergedPayload()\n        })\n      });\n\n      if (!response.ok) {\n        let message = "ZIP 생성에 실패했습니다.";\n        try {\n          const payload = await response.json();\n          if (payload && payload.error) {\n            message = payload.error;\n          }\n        } catch (error) {\n          // ignore parse failure and fall back to default message\n        }\n        throw new Error(message);\n      }\n\n      const blob = await response.blob();\n      const fileName = parseDownloadName(response.headers.get("Content-Disposition"));\n      downloadBlob(blob, fileName);\n      updateStatus("전체 JSON, 05-only JSON, HWPX가 ZIP 1개로 생성되었습니다.", "ok");\n    } catch (error) {\n      updateStatus(error.message || "ZIP 생성 중 오류가 발생했습니다.", "warn");\n    } finally {\n      bundleBtn.textContent = originalLabel;\n      bundleBtn.disabled = !state.items.length;\n    }\n  };\n\n  fileInput.addEventListener("change", (event) => addFiles(event.target.files));\n  startNumberInput.addEventListener("input", refresh);\n  clearBtn.addEventListener("click", () => {\n    state.items = [];\n    refresh();\n  });\n  bundleBtn.addEventListener("click", downloadBundle);\n  previewFullBtn.addEventListener("click", () => {\n    state.previewMode = "full";\n    updatePreview();\n  });\n  preview05Btn.addEventListener("click", () => {\n    state.previewMode = "05";\n    updatePreview();\n  });\n\n  ["dragenter", "dragover"].forEach((type) => {\n    dropZone.addEventListener(type, (event) => {\n      event.preventDefault();\n      dropZone.classList.add("dragover");\n    });\n  });\n\n  ["dragleave", "drop"].forEach((type) => {\n    dropZone.addEventListener(type, (event) => {\n      event.preventDefault();\n      dropZone.classList.remove("dragover");\n    });\n  });\n\n  dropZone.addEventListener("drop", (event) => {\n    const files = event.dataTransfer ? event.dataTransfer.files : null;\n    addFiles(files);\n  });\n\n  if (window.location.protocol === "file:") {\n    updateStatus("현재는 파일 직접 열기 모드입니다. ZIP 생성까지 쓰려면 `tools/master_analysis_bundle/START_MASTER_ANALYSIS_BUNDLE.bat`로 여세요.", "warn");\n  }\n\n  refresh();\n})();\n</script>\n</body>\n</html>\n'
GENERATOR_PATH = ROOT_DIR / "master_analysis_hwpx_generator.py"
TEMPLATE_PATH = ROOT_DIR / "analysis_template.hwpx"

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
KEY_VOCAB = "\uc5b4\ud718"
KEY_POINTS = "\ucd9c\uc81c\ud3ec\uc778\ud2b8"
REQUIRED_KEYS = [KEY_NUMBER, KEY_FULL_CONTENT, KEY_BACKGROUND, KEY_MATERIAL, KEY_TOPIC, KEY_MAIN_IDEA, KEY_TITLE, KEY_ONE_SENTENCE, KEY_TOPIC_SENTENCE, KEY_SENTENCES, KEY_VOCAB, KEY_POINTS]

class ReusableServer(ThreadingHTTPServer):
    allow_reuse_address = True


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def validate_payload(payload):
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
    candidates = [path for path in workdir.glob("*.hwpx") if path.name != TEMPLATE_PATH.name]
    if not candidates:
        raise FileNotFoundError("Generated HWPX file was not found.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_bundle(payload):
    validate_payload(payload)
    with tempfile.TemporaryDirectory(prefix="merger_lab_") as temp_dir:
        workdir = Path(temp_dir)
        merged_bytes = json_bytes(payload)
        (workdir / "MASTER_ANALYSIS_merged.json").write_bytes(merged_bytes)
        (workdir / "input.json").write_bytes(merged_bytes)
        shutil.copy2(TEMPLATE_PATH, workdir / TEMPLATE_PATH.name)
        shutil.copy2(GENERATOR_PATH, workdir / GENERATOR_PATH.name)
        completed = subprocess.run([sys.executable, str(workdir / GENERATOR_PATH.name)], cwd=workdir, capture_output=True)
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
            bundle_bytes, download_name = build_bundle(request_payload.get("mergedPayload"))
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
    for path in (GENERATOR_PATH, TEMPLATE_PATH):
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
