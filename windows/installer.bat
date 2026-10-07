@echo off
rem Installation (une seule fois). Voir installer.ps1 pour le detail.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1" %*
pause
