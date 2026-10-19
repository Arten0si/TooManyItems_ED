@echo off
chcp 65001 >nul
rem ===========================================================================
rem  Budowanie TooManyItems.exe (PyInstaller) + paczka ZIP do wydania.
rem  Uruchom dwuklikiem albo w cmd:  D:\TooManyItems_ED\release\build_exe.bat
rem  1) tworzy czyste srodowisko Pythona w release\.venv (tylko pywebview + pyinstaller)
rem  2) buduje release\dist\TooManyItems\TooManyItems.exe
rem  3) pakuje wszystko do release\TooManyItems_ED_v%VER%.zip
rem  Nic nie zmienia w folderze gry ani w plikach projektu.
rem ===========================================================================
set VER=1.0.0
cd /d "%~dp0"

where python >nul 2>nul || (echo Nie znaleziono Pythona. & pause & exit /b 1)

if not exist .venv\Scripts\python.exe (
  echo [1/3] Tworze srodowisko .venv ...
  python -m venv .venv || (echo Nie udalo sie utworzyc .venv & pause & exit /b 1)
)
echo [1/3] Instaluje pyinstaller i pywebview w .venv ...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --upgrade pip
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --upgrade "pyinstaller>=6.22" pywebview
if errorlevel 1 (echo Instalacja bibliotek nie powiodla sie. & pause & exit /b 1)

echo [2/3] Buduje TooManyItems.exe (1-3 minuty) ...
if exist dist\TooManyItems rmdir /s /q dist\TooManyItems
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --log-level WARN ^
  --distpath dist --workpath build TooManyItems.spec
if errorlevel 1 (echo Budowanie nie powiodlo sie - skopiuj Claude'owi tekst z tego okna. & pause & exit /b 1)

copy /y README.txt dist\TooManyItems\ >nul
copy /y ..\LICENSE dist\TooManyItems\LICENSE.txt >nul

echo [3/3] Pakuje ZIP ...
if exist TooManyItems_ED_v%VER%.zip del TooManyItems_ED_v%VER%.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\TooManyItems' -DestinationPath 'TooManyItems_ED_v%VER%.zip'"
powershell -NoProfile -Command "Get-FileHash 'TooManyItems_ED_v%VER%.zip' -Algorithm SHA256 | ForEach-Object { $_.Hash } | Out-File -Encoding ascii 'TooManyItems_ED_v%VER%.sha256.txt'"

echo.
echo GOTOWE:
echo   program:  %~dp0dist\TooManyItems\TooManyItems.exe
echo   paczka:   %~dp0TooManyItems_ED_v%VER%.zip
echo   SHA256:   %~dp0TooManyItems_ED_v%VER%.sha256.txt
pause
