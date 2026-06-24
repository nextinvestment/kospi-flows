@echo off
REM market_bot.exe (stock-screener) — kospi-flows + 4개 트래커 통합 봇.
REM 시작프로그램(HKCU Run: KospiFlowsBot)으로 로그인 시 자동 기동됨.
REM
REM 중복 인스턴스(텔레그램 getUpdates 409 Conflict) 방지:
REM   기존 market_bot.exe 를 전부 종료한 뒤 정확히 1개만 기동한다.
REM   이 .bat 은 언제 몇 번 실행해도(로그인/수동) 항상 단일 인스턴스를 보장한다.

taskkill /F /IM market_bot.exe >nul 2>&1
REM 종료 후 포트/폴링 정리 대기
ping -n 3 127.0.0.1 >nul

start "" "C:\Users\robust\stock-screener\market_bot.exe"
echo market_bot.exe (re)started - single instance ensured.
