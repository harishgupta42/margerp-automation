@echo off
set SCRIPT_DIR=%~dp0
set PY=python
where python >nul 2>&1
if errorlevel 1 set PY=py
set LOGDIR=%SCRIPT_DIR%hook_data
set MARGHOOK=D:\MARGERP\HOOK_DATA\bill_hook.txt
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "D:\MARGERP\HOOK_DATA" mkdir "D:\MARGERP\HOOK_DATA"
echo %DATE% %TIME% bat_ran>> "D:\MARGERP\HOOK_DATA\hook_ran.log"
echo %DATE% %TIME% args=%*>> "%LOGDIR%\last_run.txt"
if exist "%MARGHOOK%" (
  echo %DATE% %TIME% marg_hook=>> "%LOGDIR%\last_run.txt"
  type "%MARGHOOK%" >> "%LOGDIR%\last_run.txt"
) else if exist "%LOGDIR%\bill_hook.txt" (
  echo %DATE% %TIME% pipe=>> "%LOGDIR%\last_run.txt"
  type "%LOGDIR%\bill_hook.txt" >> "%LOGDIR%\last_run.txt"
)
"%PY%" "%SCRIPT_DIR%python\hook_listener.py" %1 %2 %3 %4 %5 %6
exit /b 0
