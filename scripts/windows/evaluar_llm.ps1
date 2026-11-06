# Evaluación del asistente con el modelo de lenguaje real (Ollama) en Windows.
# Se ejecuta con doble clic en EVALUAR_LLM_WINDOWS.bat (raíz del repositorio).
# Parámetros opcionales:
#   -Rapido                 prueba con 10 preguntas (unos minutos); conviene hacerla primero
#   -Modelo llama3.2:3b     otro modelo de Ollama
#   -Timeout 180            segundos de espera por respuesta
param(
    [string]$Modelo = "qwen2.5:3b",
    [switch]$Rapido,
    [int]$Timeout = 180
)
# "Continue": en Windows PowerShell 5.1, "Stop" convierte en error cualquier texto que un
# programa escriba en stderr (pip, ollama). Los errores se revisan con $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$env:PYTHONUTF8 = "1"
$Raiz = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Raiz

function Paso($n, $texto) { Write-Host ""; Write-Host "[$n/6] $texto" -ForegroundColor Cyan }
function Falla($texto) { Write-Host ""; Write-Host "ERROR: $texto" -ForegroundColor Red; Read-Host "Presione Enter para cerrar"; exit 1 }
function OllamaActivo {
    try { Invoke-RestMethod "http://localhost:11434/api/version" -TimeoutSec 3 -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

Write-Host "=== Evaluación del asistente de onboarding con LLM local ===" -ForegroundColor Green
Write-Host "Modelo: $Modelo   Carpeta: $Raiz"
Write-Host "Mantenga la computadora conectada a la corriente y sin suspender."
Write-Host "Si se interrumpe, vuelva a ejecutar: continúa donde quedó."

# 1. Python
Paso 1 "Verificando Python 3.11 o superior"
$py = $null
foreach ($c in @(@{exe = "py"; pre = @("-3")}, @{exe = "python"; pre = @()})) {
    if (Get-Command $c.exe -ErrorAction SilentlyContinue) {
        $ok = & $c.exe @($c.pre) -c "import sys;print(sys.version_info>=(3,11))" 2>$null
        if ("$ok".Trim() -eq "True") { $py = $c; break }
    }
}
if (-not $py) {
    Start-Process "https://www.python.org/downloads/windows/"
    Falla "No se encontró Python 3.11 o superior. Instálelo marcando 'Add python.exe to PATH' y vuelva a ejecutar."
}
Write-Host "Python encontrado."

# 2. Entorno virtual y dependencias
Paso 2 "Preparando el entorno (solo tarda la primera vez)"
$vpy = Join-Path $Raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    & $py.exe @($py.pre) -m venv .venv
    if (-not (Test-Path $vpy)) { Falla "No se pudo crear el entorno virtual .venv." }
}
& $vpy -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Falla "No se pudieron instalar las dependencias (revise la conexión a internet)." }

# 3. Ollama
Paso 3 "Verificando Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $local = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if (Test-Path (Join-Path $local "ollama.exe")) { $env:Path += ";$local" }
    else {
        Start-Process "https://ollama.com/download/windows"
        Falla "Ollama no está instalado. Se abrió la página de descarga: instálelo y vuelva a ejecutar este archivo."
    }
}
if (-not (OllamaActivo)) {
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (OllamaActivo); $i++) { Start-Sleep 1 }
}
if (-not (OllamaActivo)) { Falla "Ollama no responde en http://localhost:11434. Abra la aplicación Ollama y vuelva a ejecutar." }
Write-Host "Ollama activo."

# 4. Modelo
Paso 4 "Descargando el modelo $Modelo (unos 2 GB la primera vez)"
& ollama pull $Modelo
if ($LASTEXITCODE -ne 0) { Falla "No se pudo descargar el modelo $Modelo." }

# 5. Pruebas y evaluación
Paso 5 "Ejecutando pruebas y evaluación"
& $vpy -m unittest discover -s tests -t .
if ($LASTEXITCODE -ne 0) { Falla "Fallaron las pruebas del repositorio. Envíe una captura de esta ventana." }
$argsEval = @("-m", "experimentos.evaluar_generacion", "--modo", "llm_local", "--modelo", $Modelo, "--timeout", "$Timeout")
if ($Rapido) {
    $argsEval += @("--limite", "10", "--conjuntos", "reservado")
    Write-Host "Prueba rápida: 10 preguntas."
} else {
    Write-Host "Evaluación completa: 272 preguntas. En una laptop sin GPU puede tardar de 1 a 3 horas."
}
& $vpy @argsEval
if ($LASTEXITCODE -ne 0) { Falla "La evaluación terminó con error. Envíe una captura de esta ventana." }

# 6. Empaquetado
Paso 6 "Empaquetando resultados"
$etiqueta = "llm_local_" + ($Modelo -replace "[:/]", "_")
if ($Rapido) { $etiqueta += "_prueba10" }
$archivos = Get-ChildItem "resultados\v1" -File | Where-Object { $_.Name -like "*$etiqueta*" }
$zip = Join-Path $Raiz ("resultados_" + $etiqueta + "_" + (Get-Date -Format "yyyyMMdd_HHmm") + ".zip")
Compress-Archive -Path $archivos.FullName -DestinationPath $zip -Force
if (-not (Test-Path $zip)) { Falla "No se pudo crear el archivo .zip con los resultados." }
Write-Host ""
Write-Host "LISTO. Archivo de resultados:" -ForegroundColor Green
Write-Host $zip
Write-Host "Envíe ese .zip al grupo. Los archivos revision_humana_*_revisor1.csv y _revisor2.csv"
Write-Host "los califican dos personas por separado (ver docs/rubrica_revision_humana.md)."
Start-Process explorer.exe "/select,`"$zip`""
Read-Host "Presione Enter para cerrar"
