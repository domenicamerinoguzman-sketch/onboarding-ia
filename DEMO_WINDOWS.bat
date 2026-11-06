@echo off
REM Doble clic para abrir la demo: Talento Humano (nuevos ingresos), portal del colaborador, asistente y casos S1-S8.
REM Requiere haber ejecutado antes EVALUAR_LLM_WINDOWS.bat (prepara el entorno y el modelo).
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecute EVALUAR_LLM_WINDOWS.bat -Rapido para preparar el entorno.
  pause
  exit /b 1
)
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m app.servidor --casos data\casos_estudio.json %*
pause
