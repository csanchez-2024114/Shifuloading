@echo off
REM Script para activar entorno y levantar la API de HyperShifu (Windows)

REM 1. Activar entorno virtual
call .venv\Scripts\activate.bat

REM 2. Instalar dependencias (opcional, solo la primera vez o tras cambios)
pip install -r requirements.txt

REM 3. Levantar la API (FastAPI)
uvicorn main:app --reload --host 0.0.0.0 --port 5000

REM 4. (Opcional) Para el worker, abre otra terminal y ejecuta:
REM call .venv\Scripts\activate.bat
REM python -m worker.worker

pause
