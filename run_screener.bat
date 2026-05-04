@echo off
REM Daily stock screener + data sync
set PYTHON=C:\Users\1\AppData\Local\Programs\Python\Python313\python.exe
set SCRIPT=D:\stock\stock_screener.py
set DATADIR=D:\stock\data
set LOGDIR=%DATADIR%\screener\logs

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo [%date% %time%] Starting stock screener... >> "%LOGDIR%\run.log"
%PYTHON% "%SCRIPT%" >> "%LOGDIR%\run.log" 2>&1
echo [%date% %time%] Screener done (exit: %ERRORLEVEL%) >> "%LOGDIR%\run.log"

REM Copy latest data to web directory
copy /Y "%DATADIR%\screener\latest.json" "%DATADIR%\web\latest.json" >> "%LOGDIR%\run.log" 2>&1

REM Regenerate analysis data (in case backup was updated)
%PYTHON% "D:\stock\prepare_web_data.py" >> "%LOGDIR%\run.log" 2>&1
echo [%date% %time%] All done >> "%LOGDIR%\run.log"
