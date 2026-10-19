@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Stare okno (tkinter) - zapasowe.
python tmi_app.py
if errorlevel 9009 (
  echo.
  echo Nie znaleziono Pythona. Zainstaluj go z python.org i zaznacz "Add Python to PATH".
  pause
)
if errorlevel 1 pause
