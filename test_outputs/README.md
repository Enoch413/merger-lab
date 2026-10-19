# MERGER LAB 회귀 검증 출력

이 폴더의 JSON과 HWPX는 `../tests/verify_merger_lab.py`의 합성 데이터로 생성했습니다. 실제 수업 자료가 아닙니다.

- `sample_included.hwpx`, `sample_excluded.hwpx`: 발음 필드가 있는 두 지문. 첫 지문에 긴 영어·한글발음·한국어 해석과 줄바꿈, 02 대의파악의 영어 괄호를 넣었습니다.
- `sample_merged.json`: 두 옵션의 ZIP에 동일하게 포함되는 통합 JSON. `한글발음`과 `출제포인트`를 보존합니다.
- `sample_included_bundle.zip`, `sample_excluded_bundle.zip`: 실제 서버 생성 경로의 ZIP 결과.
- `legacy_excluded.hwpx`: 발음 필드가 없는 기존 형식으로 만든 미포함 결과.

다시 검증하려면 프로젝트 폴더에서 `py -3 tests/verify_merger_lab.py`를 실행하세요. 한글에서 이 폴더의 HWPX를 열어 둔 경우 파일 잠금 때문에 재생성이 실패할 수 있으므로 먼저 문서를 닫으세요.
