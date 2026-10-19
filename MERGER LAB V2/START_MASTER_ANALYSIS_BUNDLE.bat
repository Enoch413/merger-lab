@echo off
setlocal

cd /d "%~dp0"

set "URL=http://127.0.0.1:8782/"
set "HEALTH_URL=http://127.0.0.1:8782/api/health"
set "SCRIPT=MERGER_LAB_SERVER.py"

powershell -NoProfile -Command "try { $response = Invoke-WebRequest -UseBasicParsing '%HEALTH_URL%' -TimeoutSec 2; if ($response.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    start "" "%URL%"
    exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
    start "MERGER LAB V2 SERVER" /D "%~dp0" cmd /k py -3 "%SCRIPT%"
    exit /b 0
)

where python >nul 2>&1
if not errorlevel 1 (
    start "MERGER LAB V2 SERVER" /D "%~dp0" cmd /k python "%SCRIPT%"
    exit /b 0
)

echo Python was not found.
echo Install Python 3, then run this file again.
pause
exit /b 1
