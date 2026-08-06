@echo off
echo Starting Marg WhatsApp Gateway...
cd /d %~dp0nodejs

netstat -ano | findstr /C:":3030" | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo.
  echo Server is ALREADY running on port 3030.
  echo Do not start a second copy — that breaks WhatsApp sending.
  echo To restart: run STOP_SERVER.bat first, then run this again.
  echo.
  pause
  exit /b 1
)

if not exist "node_modules\@whiskeysockets\baileys" (
  echo Installing Node.js dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed. Check that Node.js is installed.
    pause
    exit /b 1
  )
)
node whatsapp_server.js
pause
