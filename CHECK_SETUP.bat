@echo off
cd /d %~dp0
python python\setup_check.py %1
pause
