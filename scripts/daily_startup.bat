@echo off
setlocal

set "ROOT=%~dp0.."
cd /d "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
	echo [ORB] Missing virtual environment at .venv\Scripts\python.exe
	echo [ORB] Run: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt
	exit /b 1
)

if /I "%ORB_ENFORCE_PREFLIGHT%"=="1" (
	powershell -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_api.ps1" -PreferredPort 8000 -BindHost 127.0.0.1 -Reload -EnforcePreflight
) else (
	powershell -ExecutionPolicy Bypass -File "%ROOT%\scripts\start_api.ps1" -PreferredPort 8000 -BindHost 127.0.0.1 -Reload
)

endlocal
