@echo off
echo Stopping market_bot.exe...
taskkill /F /IM market_bot.exe 2>nul
REM legacy: kill any stale pythonw telegram_bot.py still running
wmic process where "name='pythonw.exe' and CommandLine like '%%telegram_bot.py%%'" delete 2>nul
echo Done.
