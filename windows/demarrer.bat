@echo off
rem Demarre ComfyUI (fenetre reduite) puis surveille boite\entree.
rem Depose ma_photo.jpg + ma_photo.txt dans boite\entree ; le resultat arrive dans boite\sortie.
setlocal
set "RACINE=%~dp0.."
set "MOTEUR=%RACINE%\moteur\ComfyUI_windows_portable"
set "PY=%MOTEUR%\python_embeded\python.exe"
if not exist "%PY%" (
  echo ComfyUI introuvable : lance d'abord windows\installer.bat
  pause
  exit /b 1
)
echo Demarrage de ComfyUI...
start "ComfyUI" /min "%PY%" -s "%MOTEUR%\ComfyUI\main.py" --windows-standalone-build --disable-auto-launch --listen 127.0.0.1 --port 8188
"%PY%" "%RACINE%\lancer.py" surveiller --boite "%RACINE%\boite" --config "%RACINE%\config.json"
pause
