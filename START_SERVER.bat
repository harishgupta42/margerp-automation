@echo off
echo Starting Marg WhatsApp Gateway...
cd /d %~dp0nodejs
node whatsapp_server.js
pause
