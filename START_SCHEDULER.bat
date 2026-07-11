@echo off
echo Starting Marg Reminder Scheduler...
cd /d %~dp0python
python scheduler.py
pause
