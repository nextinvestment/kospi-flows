@echo off
echo Stopping kospi-flows telegram bot...
taskkill /F /FI "WINDOWTITLE eq telegram_bot.py*" 2>nul
REM pythonw doesn't show window title easily — kill by command-line match
wmic process where "name='pythonw.exe' and CommandLine like '%%telegram_bot.py%%'" delete 2>nul
echo Done.
