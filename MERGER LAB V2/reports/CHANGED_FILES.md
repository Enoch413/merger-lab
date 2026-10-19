# 변경 파일 목록

운영 폴더의 기존 파일은 덮어쓰지 않고 `MERGER LAB V2`에 별도 구현했다.

## 수정·교체

- `MERGER_LAB_SERVER.py`: V2/기존 호환 출력 모드, 학교·지문 구간별 범위 전달·검증, 도식 파일 ZIP 포함, 포트 8782.
- `master_analysis_hwpx_generator.py`: 논리 시각화 검증·렌더링·삽입, 학교·지문별 범위 머리말 교체, 기존 호환 모드 유지.
- `app/index.html`: 학교 입력, 범위 구간 추가·삭제, 출력 모드 선택 UI와 오류 표시.
- `index.html`: V2 제목과 안내.
- `START_MASTER_ANALYSIS_BUNDLE.bat`: 별도 V2 서버 실행.
- `analysis_template.hwpx`: 사용자 편집 `T01_microwave_excluded.hwpx` 기반 기본 템플릿.
- `analysis_template_pronunciation.hwpx`: 같은 기반에서 03 발음 줄만 추가한 템플릿.
- `README_PORTABLE.md`: 설치·실행·출력 모드·템플릿 관계 설명.

## 신규

- `logic_visualizer.py`: 승인 JSON의 Node·Edge를 FLOW/BRANCH PNG로 렌더링. `reading_order`와 반대인 의미 방향 Edge는 전용 외곽 경로로 표시.
- `hwpx_logic_embedder.py`: PNG 리소스 삽입 및 HWPX 이미지 참조 검증.
- `build_v2_templates.py`: 05 제목·자리표시자 구성.
- `promote_t01_template.py`: T01 출력물을 재사용 가능한 기본 템플릿으로 승격.
- `schemas/*.json`: V2 승인 JSON 계약.
- `tests/test_v2.py`: T01~T14, 지문 번호별 범위, 역방향 의미 Edge 및 00~04 회귀 검사.
- `tests/audit_template_parity.py`: 발음 포함·미포함 템플릿의 03 외 동일성 검사.
- `tests/fixtures/*.json`: 승인 JSON 원본 보존 사본.
- `test_outputs/**`: 시험 HWPX와 FLOW/BRANCH PNG.
- `reports/**`: diff, 테스트, 이미지 참조, 시각·인쇄, 보존, 최종 보고서.

