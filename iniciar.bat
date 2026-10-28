@echo off
title AgroSmart
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\streamlit.exe" (
  echo.
  echo No se encontro el entorno virtual de AgroSmart.
  echo Ejecuta primero el archivo: instalar.bat
  echo.
  pause
  exit /b 1
)
cd /d "%~dp0"
echo Iniciando AgroSmart... el navegador se abrira solo.
"%VENV%\Scripts\streamlit.exe" run "app.py" --server.address 0.0.0.0 --server.port 8501
pause
