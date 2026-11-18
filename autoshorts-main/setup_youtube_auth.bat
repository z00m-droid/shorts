@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [AutoShorts] Не найдено .venv. Сначала запусти install.bat.
  pause
  exit /b 1
)
echo [1/3] Устанавливаю PO Token Provider для yt-dlp...
".venv\Scripts\python.exe" -m pip install -U bgutil-ytdlp-pot-provider
if errorlevel 1 goto fail
where node >nul 2>nul
if errorlevel 1 (
  echo [2/3] Node.js не найден. Пробую установить Node.js LTS через winget...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Не найден winget. Установи Node.js LTS с https://nodejs.org/ и повтори этот файл.
    goto fail
  ) else (
    winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto fail
    set "PATH=%ProgramFiles%\nodejs;%PATH%"
  )
)
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js установлен, но не найден в PATH текущего окна. Перезапусти Windows Terminal и повтори setup_youtube_auth.bat.
  goto fail
)
echo [3/3] Загружаю и собираю локальный генератор PO Token...
set "DEST=%USERPROFILE%\bgutil-ytdlp-pot-provider"
if not exist "%DEST%\server\package.json" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $z=Join-Path $env:TEMP 'bgutil-provider.zip'; Invoke-WebRequest 'https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/heads/master.zip' -OutFile $z; Expand-Archive -Force $z (Join-Path $env:TEMP 'bgutil-provider-src'); $src=Get-ChildItem (Join-Path $env:TEMP 'bgutil-provider-src') -Directory | Select-Object -First 1; if(Test-Path $env:USERPROFILE\bgutil-ytdlp-pot-provider){Remove-Item -Recurse -Force $env:USERPROFILE\bgutil-ytdlp-pot-provider}; Move-Item $src.FullName $env:USERPROFILE\bgutil-ytdlp-pot-provider"
  if errorlevel 1 goto fail
)
cd /d "%DEST%\server"
call npm ci
if errorlevel 1 goto fail
call npx tsc
if errorlevel 1 goto fail
cd /d "%~dp0"
echo.
echo [OK] YouTube auth components installed.
echo Restart AutoShorts Studio. Sign in using the separate Edge profile in the web interface.
pause
exit /b 0
:fail
echo.
echo [ERROR] Setup did not finish. See the message above.
pause
exit /b 1
