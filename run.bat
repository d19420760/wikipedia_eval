@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" goto usage
if "%~2"=="" goto usage

set "SYSTEM_PROMPT=.\system_prompts\%~1.xml"
set "OUTPUT=runs\%~2"

uv run .\run_eval.py --questions .\questions\QS3.yaml --output "%OUTPUT%" --system-prompt-file "%SYSTEM_PROMPT%" --workers 10
if errorlevel 1 (
    echo.
    echo run_eval.py failed; skipping the Sheets upload.
    exit /b 1
)

uv run .\eval_to_sheets.py "%OUTPUT%" "https://docs.google.com/spreadsheets/d/1vx3WRGJ9by6gJt4brZvOhJJkm2HkAQB8t624LCqjzAA/edit?gid=0#gid=0"
exit /b %errorlevel%

:usage
echo Usage: run.bat ^<system-prompt^> ^<output.yaml^>
echo   e.g.  run.bat SP2 test8.yaml
echo.
echo   ^<system-prompt^>  -^> .\system_prompts\^<name^>.xml
echo   ^<output.yaml^>    -^> runs\^<file^>
exit /b 1
