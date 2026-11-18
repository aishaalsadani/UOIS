@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title UOIS Diamond Release - One-Click Environment Setup

echo ===============================================================================
echo   UOIS: Urban Operations Intelligence System - Diamond Release Setup
echo ===============================================================================
echo.

rem ---------------------------------------------------------------- 1. Python Discovery
echo [1/4] Detecting Python installation (Python 3.10 - 3.13 required)...

set "BASE_PY="

rem Priority 1: Check Anaconda / Miniconda installations
for %%P in (
  "%USERPROFILE%\anaconda3\python.exe"
  "C:\Users\%USERNAME%\anaconda3\python.exe"
  "C:\anaconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "C:\ProgramData\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "C:\miniconda3\python.exe"
) do (
  if not defined BASE_PY (
    if exist "%%~P" (
      %%~P -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and 10<=v[1]<=13 else 1)" >nul 2>&1
      if not errorlevel 1 set "BASE_PY=%%~P"
    )
  )
)

rem Priority 2: Standard Python installations
if not defined BASE_PY (
  for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
    "C:\Python313\python.exe"
  ) do (
    if not defined BASE_PY (
      if exist "%%~P" (
        %%~P -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and 10<=v[1]<=13 else 1)" >nul 2>&1
        if not errorlevel 1 set "BASE_PY=%%~P"
      )
    )
  )
)

rem Priority 3: System PATH Python (Filtering out uv and Python 3.14+)
if not defined BASE_PY (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where python 2^>nul') do (
      if not defined BASE_PY (
        set "CAND=%%I"
        echo !CAND! | findstr /i "\\uv\\ uv\\ .local\\bin WindowsApps 3.14 3.15" >nul
        if errorlevel 1 (
          "!CAND!" -c "import sys; v=sys.version_info; sys.exit(0 if v[0]==3 and 10<=v[1]<=13 else 1)" >nul 2>&1
          if not errorlevel 1 set "BASE_PY=!CAND!"
        )
      )
    )
  )
)

rem Error if no valid Python found
if not defined BASE_PY (
  echo.
  echo [ERROR] No compatible Python (3.10 - 3.13) was found on this system.
  echo.
  echo Reasons:
  echo   1. Python is not installed, or not added to PATH.
  echo   2. Python 3.14+ is installed, but PyTorch and PyYAML wheels do not support 3.14+ yet.
  echo.
  echo Recommendation:
  echo   Please install Python 3.11 (64-bit) or Anaconda Python 3.11.
  echo.
  pause
  exit /b 1
)

for /f "delims=" %%V in ('call "%BASE_PY%" --version 2^>^&1') do echo   Using: %%V (from %BASE_PY%)

rem ---------------------------------------------------------------- 2. Create Clean Virtual Environment
echo.
echo [2/4] Creating local virtual environment (.venv)...
set "VENV=%~dp0.venv"
set "VPY=%VENV%\Scripts\python.exe"

if exist "%VENV%" (
  echo   Removing old/inherited .venv folder...
  rmdir /s /q "%VENV%" 2>nul
)

"%BASE_PY%" -m venv "%VENV%"
if errorlevel 1 (
  echo [ERROR] Failed to create virtual environment in "%VENV%".
  pause
  exit /b 1
)
echo   Local .venv successfully initialized.

rem ---------------------------------------------------------------- 3. Upgrade pip and Install Dependencies
echo.
echo [3/4] Installing dependencies from requirements.txt...
echo   Upgrading pip...
"%VPY%" -m pip install --upgrade pip >nul 2>&1

echo   Installing packages (Flask, PyTorch CPU, Transformers, LightGBM, Pandas, Plotly)...
"%VPY%" -m pip install --prefer-binary -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo [ERROR] pip installation failed. Please check internet connection or permissions.
  pause
  exit /b 1
)

rem ---------------------------------------------------------------- 4. Verification Check
echo.
echo [4/4] Verifying system integrity...
"%VPY%" -c "import flask, torch, transformers, safetensors, yaml, lightgbm, pandas, scipy; print('   Dependencies verified: all core modules load cleanly.')"
if errorlevel 1 (
  echo.
  echo [WARNING] Import verification encountered an issue. BERT or Decision Lab may fall back to lightweight mode.
) else (
  echo   All machine learning and server engines verified successfully.
)

echo.
echo ===============================================================================
echo   [SUCCESS] Diamond Release installation is COMPLETE!
echo ===============================================================================
echo.
echo   To launch the entire platform:
echo     1. Double-click "run_oasis.bat"
echo     2. Your browser will automatically open: http://127.0.0.1:5000/dashboard
echo.
echo ===============================================================================
pause
exit /b 0