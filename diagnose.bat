@echo off
title MediAid diagnosis
cd /d "%~dp0"
python diagnose.py
echo.
pause
