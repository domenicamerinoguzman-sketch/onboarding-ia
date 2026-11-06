@echo off
REM Doble clic: genera los 22 borradores de bienvenida con el LLM local y las planillas para dos revisores.
REM Requiere haber ejecutado antes EVALUAR_LLM_WINDOWS.bat (entorno y modelo listos) y Ollama abierto.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecute EVALUAR_LLM_WINDOWS.bat -Rapido para preparar el entorno.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m experimentos.evaluar_bienvenida generar --modo llm_local
echo.
echo LISTO. Las planillas estan en resultados\v1\revision_bienvenida_*_revisor1.csv y _revisor2.csv
pause
