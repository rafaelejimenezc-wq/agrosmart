@echo off
title AgroSmart - Demo local (sin internet)
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\streamlit.exe" (
  echo.
  echo No se encontro el entorno. Ejecuta primero instalar.bat
  echo.
  pause
  exit /b 1
)
cd /d "%~dp0"
set "AGROSMART_DB=sqlite"
echo.
echo  ============================================
echo   AGROSMART - MODO DEMO LOCAL (sin internet)
echo  ============================================
echo   Credenciales: revisa CREDENCIALES.txt
echo.
"%VENV%\Scripts\streamlit.exe" run "app.py" --server.address 0.0.0.0 --server.port 8501
pause
