@echo off
title AgroSmart - Crear administrador
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo No se encontro el entorno. Ejecuta primero instalar.bat
  pause
  exit /b 1
)
cd /d "%~dp0"
"%VENV%\Scripts\python.exe" crear_admin.py
pause
