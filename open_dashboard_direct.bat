@echo off
setlocal
cd /d "%~dp0"
title Oasis Smart City - Direct Dashboard Launcher

echo ===============================================================================
echo   Oasis Smart City - Zero-Dependency Direct Dashboard Launcher
echo ===============================================================================
echo.
echo [INFO] Opening Output\dash_1.html directly in your default web browser...
start "" "%~dp0Output\dash_1.html"
echo [INFO] Dashboard opened successfully.
echo.
