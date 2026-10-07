@echo off
rem Mesure automatique de l'etape 1 : sonde, deux creations, une edition, avec les durees.
setlocal
set "RACINE=%~dp0.."
set "MOTEUR=%RACINE%\moteur\ComfyUI_windows_portable"
set "PY=%MOTEUR%\python_embeded\python.exe"
if not exist "%PY%" (
  echo ComfyUI introuvable : lance d'abord windows\installer.bat
  pause
  exit /b 1
)
start "ComfyUI" /min "%PY%" -s "%MOTEUR%\ComfyUI\main.py" --windows-standalone-build --disable-auto-launch --listen 127.0.0.1 --port 8188
"%PY%" "%RACINE%\lancer.py" diagnostic -o "%RACINE%\boite\diagnostic" --config "%RACINE%\config.json"
if exist "%RACINE%\boite\diagnostic\diagnostic.md" start "" notepad "%RACINE%\boite\diagnostic\diagnostic.md"
pause
