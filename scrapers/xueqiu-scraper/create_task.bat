@echo off
schtasks /create /tn "DailyStockScreener" /tr "cmd.exe /c C:\Users\1\run_screener.bat" /sc daily /st 18:00 /f
echo Done. Exit code: %ERRORLEVEL%
pause
