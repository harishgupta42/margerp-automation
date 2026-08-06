@echo off
setlocal
set DUP=%~dp0marg-whatsapp-automation

if not exist "%DUP%" (
  echo No duplicate folder found — nothing to remove.
  pause
  exit /b 0
)

echo.
echo This removes the accidental nested copy:
echo   %DUP%
echo.
echo Step 1 — close anything using it:
echo   - Every "Marg WhatsApp Gateway" CMD window  ^(click X^)
echo   - File Explorer if open inside marg-whatsapp-automation
echo.
pause

echo.
echo Stopping Node processes tied to the duplicate folder...
for /f "tokens=2 delims=," %%a in ('wmic process where "name='node.exe'" get ProcessId^,CommandLine /format:csv 2^>nul ^| findstr /i "marg-whatsapp-automation\\marg-whatsapp-automation"') do (
  echo   Killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

echo Waiting 3 seconds for locks to clear...
timeout /t 3 /nobreak >nul

echo Removing folder...
rmdir /s /q "%DUP%" 2>nul

if exist "%DUP%" (
  echo.
  echo STILL IN USE — try this:
  echo   1. Close ALL Marg WhatsApp Gateway CMD windows
  echo   2. Close File Explorer in that folder
  echo   3. Restart Cursor, then run this script again
  echo.
  echo Or reboot the PC, then double-click this file once.
  pause
  exit /b 1
)

echo.
echo Done. Duplicate folder removed.
echo Use only: %~dp0START_SERVER.bat
echo.
pause
