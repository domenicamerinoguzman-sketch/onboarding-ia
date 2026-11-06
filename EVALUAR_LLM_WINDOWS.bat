@echo off
REM Doble clic para evaluar el asistente con el modelo de lenguaje real (Ollama).
REM Prueba rapida (10 preguntas):  EVALUAR_LLM_WINDOWS.bat -Rapido
REM Otro modelo:                   EVALUAR_LLM_WINDOWS.bat -Modelo llama3.2:3b
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\evaluar_llm.ps1" %*
