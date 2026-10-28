@echo off
title AgroSmart - Servidor IoT
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\uvicorn.exe" (
  echo.
  echo No se encontro el entorno. Ejecuta primero instalar.bat
  echo.
  pause
  exit /b 1
)
cd /d "%~dp0"
echo.
echo Servidor IoT de AgroSmart
echo   Documentacion: http://localhost:8000/docs
echo   Deja esta ventana abierta mientras uses el ESP32.
echo.
"%VENV%\Scripts\uvicorn.exe" iot_server:app --host 0.0.0.0 --port 8000
pause
