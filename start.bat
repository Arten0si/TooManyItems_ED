@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Nowe okno (tmi_gui.py). Przy pierwszym uruchomieniu doinstalowuje biblioteke okna pywebview.
python -c "import webview" 2>nul
if errorlevel 9009 goto nopython
if errorlevel 1 (
  echo Pierwsze uruchomienie: instaluje biblioteke okna pywebview...
  python -m pip install --user --disable-pip-version-check pywebview
  echo.
)
python tmi_gui.py
if errorlevel 9009 goto nopython
if errorlevel 1 pause
goto :eof

:nopython
echo.
echo Nie znaleziono Pythona. Zainstaluj go z python.org i zaznacz "Add Python to PATH".
pause
