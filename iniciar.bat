@echo off
echo.
echo  ==============================
echo   MuleroChat - Iniciando...
echo  ==============================
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo Creando entorno virtual...
    uv venv
)

echo Instalando dependencias...
uv pip install -e . --index-url https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple --allow-insecure-host pypi.ci.artifacts.walmart.com

echo.
echo Servidor listo en:
echo   http://localhost:8765
echo.
echo Admin por defecto:  Manfred / PIN: 1234
echo CAMBIA EL PIN del admin despues de instalar!
echo.

uv run uvicorn main:app --host 0.0.0.0 --port 8765 --reload

pause
