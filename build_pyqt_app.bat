@echo off
setlocal

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado em venv\Scripts\python.exe
    echo Crie o ambiente virtual e instale as dependencias antes de rodar este script.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"

if exist "build" rmdir /s /q "build"
if exist "dist\ICATU.exe" del /f /q "dist\ICATU.exe"

python -m PyInstaller --noconfirm --onefile --windowed --name ICATU pyqt_app.py
if errorlevel 1 (
    echo.
    echo Falha ao gerar o executavel.
    pause
    exit /b 1
)

echo.
echo Executavel gerado com sucesso em:
echo dist\ICATU.exe
pause
