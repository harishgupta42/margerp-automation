@echo off
set SCRIPT_DIR=%~dp0
set PY=python
where python >nul 2>&1
if errorlevel 1 set PY=py
"%PY%" "%SCRIPT_DIR%python\hook_listener.py" %1 %2 %3 %4 %5 %6
exit /b 0
