@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 app\sync.py) else (python app\sync.py)
exit /b %errorlevel%
