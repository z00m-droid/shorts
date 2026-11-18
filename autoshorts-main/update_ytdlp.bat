@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Не найдено .venv & pause & exit /b 1)
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]"
if errorlevel 1 (echo Обновление yt-dlp не удалось. Проверь интернет и повтори. & pause & exit /b 1)
echo yt-dlp обновлён.
pause
