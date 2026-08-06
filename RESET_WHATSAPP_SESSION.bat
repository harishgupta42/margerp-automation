@echo off
setlocal
echo ============================================================
echo  RESET WhatsApp Session
echo  Creates a fresh login — you will scan QR code again.
echo ============================================================
echo.
echo This will:
echo   1. Stop the WhatsApp server
echo   2. Backup the old session to nodejs\wa_session_backup\
echo   3. Delete the old session so a new QR login can be created
echo.
set /p CONFIRM="Continue? Type YES and press Enter: "
if /I not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)

echo.
echo Stopping server...
powershell -NoProfile -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*whatsapp_server*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 3 /nobreak >nul

cd /d %~dp0nodejs
set SESSION=wa_session
set BACKUP=wa_session_backup

if not exist "%SESSION%" (
  echo No existing session found — nothing to backup.
  goto start_fresh
)

echo Backing up old session...
if exist "%BACKUP%" rmdir /s /q "%BACKUP%" 2>nul
mkdir "%BACKUP%" 2>nul
xcopy /E /I /Q "%SESSION%" "%BACKUP%\" >nul 2>&1
if errorlevel 1 (
  echo Backup failed — session folder may be locked.
  echo Close START_SERVER.bat and Task Manager Node tasks, then run this again.
  pause
  exit /b 1
)

echo Removing old session...
rmdir /s /q "%SESSION%" 2>nul
if exist "%SESSION%" (
  echo Could not delete wa_session — folder still in use.
  echo Run STOP_SERVER.bat, close all server CMD windows, then try again.
  pause
  exit /b 1
)

:start_fresh
echo.
echo ============================================================
echo  Session cleared.
echo.
echo  NEXT STEPS:
echo    1. Run START_SERVER.bat
echo    2. A QR code will appear in the CMD window
echo    3. On your phone: WhatsApp - Settings - Linked devices
echo       - Link a device - Scan the QR code
echo    4. Wait for: WhatsApp connected! Server ready on port 3030
echo    5. Save a test bill in Marg and press Y
echo ============================================================
echo.
pause
