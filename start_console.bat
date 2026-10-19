@echo off
chcp 65001 >nul
cd /d "%~dp0"
python tmi_core.py
pause
