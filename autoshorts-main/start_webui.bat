@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [AutoShorts] Не найдено виртуальное окружение .venv.
  echo Сначала запусти install.bat или активируй окружение вручную.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" webui.py
pause
