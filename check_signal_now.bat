@echo off
REM Manual one-shot trigger for the signal bot (temporary, while it's not
REM running on a 24/7 host). Double-click this whenever you want a check --
REM it evaluates the two most-recently-closed 4H candles as of right now
REM and sends a Telegram alert only if RSI zone + CRT confirm. See
REM signals/crt_rsi_signal.py and CLAUDE.md for the logic this runs.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python signal_bot.py --once
echo.
echo Done. Check Telegram for any alert.
pause
