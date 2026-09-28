# Registro de cambios

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
