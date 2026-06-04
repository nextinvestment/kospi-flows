@echo off
cd /d %~dp0
set LOG=data\daily_run_%RANDOM%.log
python run_daily.py > %LOG% 2>&1
python push_and_notify.py >> %LOG% 2>&1
echo Wrote %LOG%
