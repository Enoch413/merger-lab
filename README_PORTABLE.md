# MERGER LAB — 다른 Windows 컴퓨터에서 실행

1. ZIP 파일을 압축 해제합니다. 내부의 `MERGER LAB` 폴더와 파일 구조를 그대로 유지하세요.
2. 해당 컴퓨터에 Python 3가 없다면 https://www.python.org/downloads/ 에서 설치합니다. 설치 시 Python Launcher(`py`)를 포함하세요.
3. 명령 프롬프트에서 `py -3 -m pip install lxml`을 한 번 실행합니다. `py`가 없고 `python` 명령을 사용할 수 있다면 `python -m pip install lxml`을 실행하세요.
4. `START_MASTER_ANALYSIS_BUNDLE.bat`을 더블클릭합니다. 브라우저가 열리지 않으면 `http://127.0.0.1:8781/`에 접속하세요.
5. JSON을 업로드하고 발음 미포함/발음 포함을 선택해 통합 JSON과 HWPX가 든 ZIP을 다운로드합니다. 발음 포함을 선택한 경우 모든 문장에 `한글발음` 문자열이 있어야 합니다.

Python과 lxml은 이 ZIP에 포함되지 않습니다. HWPX 파일을 열거나 편집하려면 해당 컴퓨터에 HWPX를 지원하는 문서 프로그램이 필요합니다. 서버는 해당 컴퓨터의 `127.0.0.1`에서만 실행됩니다. 화면에 쓰는 Google 글꼴은 인터넷 연결이 없으면 대체 글꼴로 표시될 수 있지만 문서 생성은 로컬에서 진행됩니다.
