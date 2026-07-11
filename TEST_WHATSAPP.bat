@echo off
echo Test WhatsApp send to a REAL mobile number (10 digits, no +91 needed)
echo.
set /p MOB="Enter mobile number: "
cd /d %~dp0
python python\test_send.py %MOB%
pause
