# Registro de cambios

## [1.1.0] - 2026-11-06

Responde a la revisión del avance: evaluación con el LLM real, línea base con datos del HRIS y
validación con usuarios de Talento Humano (OE4 y OE5).

### Agregado
- `EVALUAR_LLM_WINDOWS.bat` y `scripts/windows/evaluar_llm.ps1`: evaluación con Ollama en Windows de
  principio a fin (instalación, descarga del modelo, pruebas, evaluación, empaquetado).
- `evaluar_generacion.py`: `--url`, `--timeout`, `--conjuntos`, `--limite`; calentamiento del modelo;
  reanudación tras una interrupción; registro del equipo y del modelo; errores del LLM;
  dos copias de la muestra para revisión humana independiente.
- `experimentos/analizar_revision_humana.py`: acuerdo entre revisores (kappa), alucinación humana,
  utilidad e IC de Wilson.
- `experimentos/linea_base_real.py`: contraste de la línea base con el HRIS y la bitácora, con etiquetas.
- `experimentos/analizar_estudio_usuarios.py`: sesiones cronometradas (diseño cruzado), SUS,
  satisfacción, usabilidad y reducción estimada sobre el proceso completo.
- Protocolo de validación empírica con carta, consentimiento e instrumentos (`docs/validacion_empirica/`),
  plantillas y ejemplos sintéticos (`data/reales/`), casos de estudio S1–S8, escenarios de usabilidad,
  políticas sintéticas en PDF y `DEMO_WINDOWS.bat`.
- `tests/ollama_simulado.py` y `tests/test_validacion_empirica.py` (45 pruebas en total).

### Cambiado
- Los CSV de evaluación registran el origen de cada respuesta (`origen_respuesta`); la fidelidad se
  guarda como 0/1. Corregido el conteo de derivaciones del LLM, que siempre daba 0.
- `.gitignore` excluye los datos y resultados reales de la institución.

## [1.0.0] - 2026-10-26

### Agregado
- **Generación en modo dual** (`src/generacion.py`): LLM local con Ollama (`qwen2.5:3b`, temperatura 0)
  y respaldo extractivo; prompt v2 con pasajes delimitados como datos.
- **Guardas** (`src/guardas.py`): detección de inyección de instrucciones, enmascaramiento de datos
  personales y verificador de fidelidad (cita recuperada y cifras respaldadas).
- **Recuperación híbrida**: diccionario de sinónimos (`data/sinonimos.json`) y componente de n-gramas
  de caracteres; descomposición exacta del puntaje por término en cada respuesta.
- **Flujos de automatización** (`src/flujos/`): orquestador TO-BE de 13 tareas en días hábiles,
  conectores simulados (HRIS, mesa de servicios, directorio, correo), plantillas y escalamiento.
- **Demo web** (`app/`), con biblioteca estándar, y notebook ejecutado `notebooks/demo_prototipo.ipynb`.
- **Conjunto de prueba reservado** de 110 preguntas, escrito tras congelar el modelo.
- Experimentos: `validacion_v1`, `prueba_final`, `robustez`, `evaluar_generacion`, `graficos_v1`,
  `reproducir_todo`.
- 29 pruebas nuevas (35 en total), incluido un servidor Ollama simulado.
- Registro mínimo de interacciones (`--registrar`), rúbrica de revisión humana y diagrama de arquitectura.

### Cambiado
- Modelo final: B3 (sinónimos + caracteres), umbral 4,563. La configuración de v0.2 queda en
  `config/modelo_v0.2.json`.
- `src/asistente.py` ahora ejecuta el pipeline completo y devuelve trazabilidad.
- `elegir_reglas` y `decisiones` admiten una segunda señal de derivación (cobertura).

### Evaluado y descartado
- Derivación por cobertura de la consulta: sin aporte (umbral 0 en 45 de 50 pliegues).

### Corregido
- Dos patrones de inyección no detectados en la primera prueba de seguridad (S02, S13).

## [0.2.0] - 2026-09-28

### Agregado
- Etapa de recuperación del asistente RAG (`src/`):
  - preprocesamiento en español (tildes, palabras vacías, raíces Snowball);
  - recuperadores baseline, TF-IDF y BM25;
  - umbral de derivación a Talento Humano.
- Corpus sintético de 46 pasajes y 162 preguntas etiquetadas.
- Validación cruzada estratificada 10×5 con ablación, rejilla de 120 configuraciones, bootstrap pareado, McNemar y Wilcoxon.
- Plantilla de prompt para la etapa generativa. Todavía no se ha ejecutado.
- Pruebas unitarias, `requirements.txt` y figura de resultados.

### Cambiado
- Reglas de escalamiento: incorporan acceso remoto y aprobación especial, y registran el motivo de cada alerta (corrige C075).

## [0.1.0] - 2026-09-25
- Baseline de reglas y evaluación sobre 80 casos sintéticos (carpeta `v0_reglas/`).
