@echo off
echo Stopping ALL Marg WhatsApp Gateway servers...
echo.

powershell -NoProfile -Command ^
  "$procs = Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*whatsapp_server*' }; if ($procs) { $procs | ForEach-Object { Write-Host ('  Killing PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } } else { Write-Host '  No whatsapp_server.js process found.' }"

echo.
echo Also close every CMD window titled:
echo   "Marg WhatsApp Gateway"  or  "C:\WINDOWS\system32\cmd.exe"
echo   that you opened via START_SERVER.bat
echo.
echo If Task Manager still shows Node.js after this, you have another
echo START_SERVER.bat window open — close it with X, do not End Task one-by-one.
echo.
pause
