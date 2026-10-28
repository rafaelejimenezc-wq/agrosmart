@echo off
title Instalar / autenticar Google Earth Engine
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo No se encontro el entorno. Ejecuta primero instalar.bat
  pause
  exit /b 1
)
echo Instalando earthengine-api...
"%VENV%\Scripts\python.exe" -m pip install earthengine-api
echo.
echo Autenticando con Google (se abrira el navegador)...
"%VENV%\Scripts\earthengine.exe" authenticate
echo.
echo Listo. Recuerda registrarte en https://code.earthengine.google.com/register
pause
