@echo off
REM market_bot.exe (stock-screener) - unified bot: kospi-flows + 4 trackers.
REM Auto-started at logon via HKCU Run key "KospiFlowsBot".
REM
REM Prevents duplicate instances (Telegram getUpdates 409 Conflict):
REM kills any running market_bot.exe first, then starts exactly one.
REM Safe to run any number of times (logon or manual) - always single instance.
REM NOTE: ASCII-only comments (cmd reads this file in the system codepage; UTF-8
REM Korean here corrupts and gets executed as commands).

taskkill /F /IM market_bot.exe >nul 2>&1
ping -n 3 127.0.0.1 >nul

start "" "C:\Users\robust\stock-screener\market_bot.exe"
echo market_bot.exe (re)started - single instance ensured.
