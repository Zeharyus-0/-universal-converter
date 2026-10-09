@echo off
rem UNIVERSAL CONVERTER by zeharyus
rem Builds "Universal Converter.exe" once. Copy the .exe from the dist folder to any PC.
rem Needs Python on THIS PC only (python.org, tick "Add python.exe to PATH").
setlocal
cd /d "%~dp0"

set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python was not found on this PC.
  echo Install it from python.org and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

echo [1/3] Creating build environment in .buildenv
%PY% -m venv .buildenv || goto :fail

echo [2/3] Installing PySide6, Pillow, FFmpeg (imageio-ffmpeg), PyInstaller
".buildenv\Scripts\python.exe" -m pip install --disable-pip-version-check PySide6==6.12.0 Pillow==12.1.1 imageio-ffmpeg==0.6.0 pyinstaller==6.22.3 || goto :fail

echo [3/3] Building the exe
".buildenv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "Universal Converter" --icon assets\icon.ico --add-data "fonts:fonts" --add-data "assets:assets" universal_converter.py || goto :fail

echo.
echo Done: dist\Universal Converter.exe
explorer dist
pause
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the first red/ERROR line.
pause
exit /b 1
