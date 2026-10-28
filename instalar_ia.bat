@echo off
title Instalar IA de plagas
set "VENV=%USERPROFILE%\agrosmart-venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo No se encontro el entorno. Ejecuta primero instalar.bat
  pause
  exit /b 1
)
echo Instalando PyTorch (version CPU, ~150 MB)...
"%VENV%\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
echo Instalando Transformers...
"%VENV%\Scripts\python.exe" -m pip install transformers
echo.
echo Listo. La primera vez que analices una imagen se descargara el modelo.
pause
