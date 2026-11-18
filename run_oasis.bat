@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title UOIS - Urban Operations Intelligence System - launcher

echo ===============================================================================
echo   UOIS - Urban Operations Intelligence System: server + BERT + dashboard
echo ===============================================================================
echo.

set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"

rem ---------------------------------------------------------------- 1. Python environment (.venv)
rem Only Python 3.10 to 3.13 is supported. Python 3.14+ (e.g. uv) is strictly ignored:
rem pyyaml / torch wheels are missing there, and uv environments block pip wheel installation.
echo [1/5] Python environment ^(.venv with Python 3.13 / 3.12 / 3.11 / 3.10^)...

rem Manual clean-slate flag support: run_oasis.bat --clean
if /i "%~1"=="--clean" set "FORCE_CLEAN=1"
if /i "%~1"=="clean"   set "FORCE_CLEAN=1"
if /i "%~1"=="/clean"  set "FORCE_CLEAN=1"

if defined FORCE_CLEAN (
  call :yellow "  [CLEAN] Removing existing .venv folder as requested..."
  if exist "%VENV%" rmdir /s /q "%VENV%" 2>nul
)

rem Automatic clean-slate if .venv exists but is broken or incomplete
if exist "%VENV%" (
  call :check_python "%VPY%"
  if "!IS_VALID!"=="1" (
    goto have_venv
  )
  call :yellow "  [NOTICE] The existing .venv uses an unsupported, broken, or foreign Python environment."
  call :yellow "           Automatically removing corrupted .venv to rebuild with clean Python 3.11..."
  rmdir /s /q "%VENV%" 2>nul
  if exist "%VENV%" (
    call :yellow "           Could not delete .venv directly (in use); renaming to backup folder..."
    ren "%VENV%" ".venv_corrupted_%RANDOM%" 2>nul
  )
)

set "BASE="

rem Priority 1: Prioritize Anaconda / Miniconda installations (Python 3.11)
for %%P in (
  "C:\Users\abdel\anaconda3\python.exe"
  "%USERPROFILE%\anaconda3\python.exe"
  "C:\anaconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "C:\ProgramData\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "C:\miniconda3\python.exe"
) do (
  if not defined BASE (
    call :check_python "%%~P"
    if "!IS_VALID!"=="1" set BASE="%%~P"
  )
)

rem Priority 2: Standard Python Foundation installations (3.13 -> 3.12 -> 3.11 -> 3.10)
if not defined BASE (
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-3.12-64\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-3.11-64\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-3.10-64\python.exe"
  ) do (
    if not defined BASE (
      call :check_python "%%~P"
      if "!IS_VALID!"=="1" set BASE="%%~P"
    )
  )
)

rem Priority 3: Windows Python Launcher 'py'
if not defined BASE (
  for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined BASE (
      py -%%V -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and 10<=v[1]<=13 else 1)" >nul 2>&1
      if not errorlevel 1 set "BASE=py -%%V"
    )
  )
)

rem Priority 4: Filter system PATH via 'where python'
rem EXPLICITLY ignore any path containing 'uv', '3.14', '3.15', '.local\bin', or 'WindowsApps'
if not defined BASE (
  for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined BASE (
      set "CAND=%%I"
      echo !CAND! | findstr /i "\\uv\\ uv\\ .local\\bin 3.14 3.15 WindowsApps" >nul
      if errorlevel 1 (
        call :check_python "!CAND!"
        if "!IS_VALID!"=="1" set BASE="!CAND!"
      )
    )
  )
)

if not defined BASE (
  call :red "[ERROR] No valid Python 3.10, 3.11, 3.12, or 3.13 was found."
  call :red "        Python 3.14+ and uv-managed Pythons are ignored because binary wheels"
  call :red "        (torch, transformers, pyyaml) do not support them."
  echo.
  echo   Please ensure Anaconda Python 3.11 is installed or install Python 3.11/3.12/3.13.
  echo   The data pages still work without Python: open oasis_city_system.html directly.
  pause
  exit /b 1
)

for /f "delims=" %%V in ('call %BASE% --version 2^>^&1') do echo   creating .venv with %%V  ^(%BASE%^)
call %BASE% -m venv "%VENV%"
if errorlevel 1 (
  call :red "[ERROR] Could not create the .venv folder using %BASE%."
  pause
  exit /b 1
)

:have_venv
for /f "delims=" %%V in ('call "%VPY%" --version 2^>^&1') do echo   using %%V  ^(.venv\Scripts\python.exe^)

rem ---------------------------------------------------------------- 2. requirements
echo.
echo [2/5] Checking requirements ^(flask, torch CPU, transformers, pyyaml; simulator: numpy, pandas, scipy^)...
"%VPY%" -c "import flask, torch, transformers, safetensors, yaml" >nul 2>&1
if errorlevel 1 (
  echo   Missing packages. Installing requirements.txt into .venv ^(first run only^).
  echo   CPU-only PyTorch + transformers: about 150 MB download, about 620 MB on disk.
  "%VPY%" install_requirements.py
  if errorlevel 1 (
    echo.
    call :red "[ERROR] Installing the requirements failed (the real pip error is printed above in red)."
    call :red "        The server was NOT started. Fix the error above, then run run_oasis.bat again."
    pause
    exit /b 1
  )
) else (
  echo   all present.
)
rem Decision Lab (added): Ayat's 60-day simulator needs numpy, pandas, scipy; the tests need pytest. Optional:
rem if they cannot be installed the server and BERT still start, and /api/health says why the simulator is off.
"%VPY%" -c "import numpy, pandas, scipy, pytest" >nul 2>&1
if errorlevel 1 (
  echo   Installing the Decision Lab packages ^(numpy, pandas, scipy, pytest^) into .venv ^(once^)...
  "%VPY%" install_requirements.py --groups simulator,tests
  if errorlevel 1 call :red "  [WARNING] Decision Lab packages not installed; the server starts without the simulator."
)

rem ---------------------------------------------------------------- 3. start server
echo.
echo [3/5] Starting citizen_app.py on http://127.0.0.1:5000 ...
powershell -NoProfile -Command "try{Invoke-RestMethod http://127.0.0.1:5000/api/health -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
  powershell -NoProfile -Command "try{$h=Invoke-RestMethod http://127.0.0.1:5000/api/health -TimeoutSec 2; if($h.bert_loaded){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
  if errorlevel 1 (
    call :red "[ERROR] Another server is already running on port 5000 and it has NOT loaded BERT"
    call :red "        (probably an older one started with Python 3.15). Close its 'UOIS server' window,"
    call :red "        then run run_oasis.bat again."
    pause
    exit /b 1
  )
  echo   a server with BERT loaded is already answering on port 5000; using it.
) else (
  start "UOIS server - close this window to stop" "%VPY%" -u citizen_app.py
)

rem ---------------------------------------------------------------- 4. wait for /api/health
echo.
echo [4/5] Waiting for the server to answer ^(loading BERT can take up to a minute^)...
set /a TRIES=0
:wait
set /a TRIES+=1
powershell -NoProfile -Command "try{Invoke-RestMethod http://127.0.0.1:5000/api/health -TimeoutSec 2 | Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto ready
if !TRIES! GEQ 90 (
  call :red "[ERROR] No answer after about 3 minutes. Check the 'UOIS server' window for errors."
  pause
  exit /b 1
)
timeout /t 2 /nobreak >nul
goto wait

:ready
echo   server is up.
echo.
echo ---------------------------------------------------------------- model report
for /f "delims=" %%V in ('call "%VPY%" --version 2^>^&1') do echo   Python                 : %%V ^(.venv^)
powershell -NoProfile -Command ^
 "$h=Invoke-RestMethod http://127.0.0.1:5000/api/health;" ^
 "Write-Host ('  PyTorch installed      : ' + $h.torch_installed);" ^
 "Write-Host ('  transformers installed : ' + $h.transformers_installed);" ^
 "$h.model_files.PSObject.Properties | ForEach-Object { Write-Host ('  model file ' + $_.Name.PadRight(22) + ': ' + $_.Value) };" ^
 "if($h.bert_loaded){Write-Host '  INFERENCE_ENGINE       : BERT model LOADED (MARBERTv2 fine-tuned)' -ForegroundColor Green}" ^
 "else{Write-Host '  INFERENCE_ENGINE       : FELL BACK to the keyword classifier - BERT is NOT loaded' -ForegroundColor Red; Write-Host ('  reason                 : ' + $h.load_error) -ForegroundColor Red; Write-Host '  The dashboard will show no classification results until BERT loads.' -ForegroundColor Red}" ^
 "$s=$h.simulator_60d; if($s -and $s.loaded){Write-Host ('  Simulator 60d          : LOADED (' + $s.n_sims + ' draws, ' + $s.dates[0] + ' to ' + $s.dates[1] + ') - Decision Lab ready') -ForegroundColor Green}" ^
 "else{Write-Host '  Simulator 60d          : NOT loaded - the Decision Lab page will show the offline message' -ForegroundColor Red; if($s){Write-Host ('  reason                 : ' + $s.error) -ForegroundColor Red}}" ^
 "if(-not $h.dashboard_file){Write-Host '  [WARNING] oasis_city_system.html not found next to citizen_app.py or one folder up.' -ForegroundColor Yellow}"
echo -------------------------------------------------------------------------------

rem ---------------------------------------------------------------- 5. open the dashboard
echo.
echo [5/5] Opening http://127.0.0.1:5000/dashboard in your default browser...
start "" "http://127.0.0.1:5000/dashboard"
echo.
echo   Original pages still served: /portal  /model-analytics  /forecast (dash_1 forecast)
echo   To stop: close the "UOIS server" window.
echo.
pause
exit /b 0

:check_python
set "IS_VALID=0"
if not exist "%~1" exit /b 0
"%~1" -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and 10<=v[1]<=13 else 1)" >nul 2>&1
if not errorlevel 1 set "IS_VALID=1"
exit /b 0

:red
set "MSG=%~1"
powershell -NoProfile -Command "Write-Host $env:MSG -ForegroundColor Red" 2>nul
if errorlevel 1 echo %~1
exit /b 0

:yellow
set "MSG=%~1"
powershell -NoProfile -Command "Write-Host $env:MSG -ForegroundColor Yellow" 2>nul
if errorlevel 1 echo %~1
exit /b 0

:green
set "MSG=%~1"
powershell -NoProfile -Command "Write-Host $env:MSG -ForegroundColor Green" 2>nul
if errorlevel 1 echo %~1
exit /b 0
