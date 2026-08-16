@echo off
rem Run on Windows. Uses its own venv .venv-win (separate from Linux/WSL .venv).
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 goto :usepy
where python >nul 2>nul
if %errorlevel%==0 goto :usepython
echo Khong tim thay Python. Vui long cai Python 3.10+ tu python.org
pause
exit /b 1

:usepy
set "PYCMD=py -3"
goto :check

:usepython
set "PYCMD=python"
goto :check

:check
if exist .venv-win\Scripts\python.exe goto :run
echo Tao moi truong ao .venv-win va cai dependencies lan dau...
%PYCMD% -m venv .venv-win
.venv-win\Scripts\python -m pip install -U pip
.venv-win\Scripts\python -m pip install -r requirements.txt

:run
.venv-win\Scripts\python main.py
