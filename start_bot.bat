@echo off
cd /d %~dp0
REM Detached background launch (no console window). Logs go to data/bot.log.
start "" /B pythonw.exe telegram_bot.py >> data\bot.log 2>&1
echo Bot started in background. Tail data\bot.log to monitor.
