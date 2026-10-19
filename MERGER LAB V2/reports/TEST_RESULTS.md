# 전체 테스트 결과

실행일: 2026-10-15

## 자동화 검사

- `py -3 -m unittest discover -s tests -p 'test_*.py' -v`: 13/13 PASS.
- `py -3 tests/verify_merger_lab.py`: 7/7 PASS.
- `py -3 tests/audit_template_parity.py`: PASS.
- 총 기존·신규 단위/통합 테스트: 20/20 PASS, 템플릿 동일성 감사 추가 PASS.

## T01~T14

| ID | 결과 | 확인 내용 |
|---|---|---|
| T01 | PASS | 전자레인지, 발음 미포함, V2 HWPX·FLOW PNG |
| T02 | PASS | 전자레인지, 발음 포함, V2 HWPX·FLOW PNG |
| T03 | PASS | 애도, 발음 미포함, V2 HWPX·BRANCH PNG |
| T04 | PASS | 애도, 발음 포함, V2 HWPX·BRANCH PNG |
| T05 | PASS | 전자레인지→애도, 발음 미포함, 이미지 ID 2개 고유 |
| T06 | PASS | 전자레인지→애도, 발음 포함, 이미지 ID 2개 고유 |
| T07 | PASS | 애도→전자레인지, 발음 미포함, 입력 순서 보존 |
| T08 | PASS | 애도→전자레인지, 발음 포함, 입력 순서 보존 |
| T09 | PASS | 구형 JSON, 기존 호환 모드, 05 없음 |
| T10 | PASS | 존재하지 않는 Edge 대상 ID 오류 탐지 |
| T11 | PASS | manifest에 없는 HWPX 이미지 참조 오류 탐지 |
| T12 | PASS | V2에서 논리 시각화 누락 오류 탐지 |
| T13 | PASS | 학교·범위 머리말, 다중 지문, 발음 포함, JSON 비변경 |
| T14 | PASS | 최종 지문 번호별 범위 구간, 겹침·누락·범위 밖 번호 차단, 기존 단일 범위 호환 |

추가로 발음 누락·빈 문자열·잘못된 자료형의 지문/문장 위치 안내, JSON 동일 보존, UI 기본값과 HTTP 옵션 전달, 학교·범위 문자열 검증, 주제문 강조, 다중 문장, 긴 문장 자동 높이를 검사했다. `1~10 / Q미니S 10강`, `11~20 / Q미니S 11강` 직접 매핑과 4개 지문 HWPX의 지문별 머리말도 확인했다.

BRICs 담수 원본 JSON의 `N3`→`N1` Edge도 발음 포함·미포함 양쪽에서 생성했다. 두 통합 JSON은 원본과 동일했고, 두 HWPX의 `logic_001` 이미지 참조가 정상이며, 외곽 우회 화살표가 PNG에서 가려지지 않는 것을 확인했다.

