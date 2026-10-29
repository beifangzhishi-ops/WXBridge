@echo off
setlocal
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m wxbridge %*
exit /b %ERRORLEVEL%
