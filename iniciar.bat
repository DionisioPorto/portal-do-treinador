@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale o Python em https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Instalando dependencias (primeira vez pode demorar)...
python -m pip install -r requirements.txt --quiet

echo.
echo Abrindo o portal no navegador...
start "Portal do Treinador" cmd /k python app.py
timeout /t 3 >nul
start "" "http://127.0.0.1:5000"
exit /b 0