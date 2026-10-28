@echo off
title Instalador de AgroSmart
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
  echo.
  echo No se encontro Python 3.12 en:
  echo   %PY%
  echo.
  echo Instalalo abriendo PowerShell y ejecutando:
  echo   winget install --id Python.Python.3.12 -e --scope user
  echo.
  pause
  exit /b 1
)
set "VENV=%USERPROFILE%\agrosmart-venv"
echo Creando entorno virtual en %VENV% ...
if not exist "%VENV%" "%PY%" -m venv "%VENV%"
echo Instalando librerias (puede tardar unos minutos)...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
echo.
echo Listo. Ahora ejecuta: iniciar.bat
pause
