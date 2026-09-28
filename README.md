# Asistente de onboarding con IA: prototipo v0.2

Proyecto de titulación de la Maestría en Inteligencia Artificial Aplicada (UDLA), Grupo 1:
María Doménica Merino, Limber Mosquera e Ivonne Moscoso.

*Desarrollo de un sistema inteligente para la automatización del proceso de onboarding mediante
IA Generativa y Automatización Inteligente de Procesos en una institución financiera en Ecuador.*

## Qué contiene

El sistema propuesto separa dos componentes:

| Componente | Tipo | Estado en v0.2 |
|---|---|---|
| Asistente de consultas del nuevo colaborador (RAG) | **IA**: recuperación de pasajes de política + generación con LLM | Recuperación implementada y validada. Generación **especificada, no ejecutada** (`prompts/`) por falta de acceso a una API de LLM |
| Reglas de escalamiento a Talento Humano | **Automatización tradicional** (sin IA) | Corregidas: incluyen acceso remoto y aprobación especial, con motivo trazable |

**Todos los datos son sintéticos.** El corpus (`data/corpus/politicas_induccion.md`) son 46 pasajes
de 10 políticas de inducción *ficticias* redactadas por el equipo. Las 162 preguntas
(`data/preguntas_evaluacion.csv`) también fueron escritas por el equipo: 46 directas, 92
parafraseadas y 24 fuera del alcance. Ninguna cifra de este repositorio mide desempeño en una
organización real.

## Estructura

```
data/            corpus sintético y preguntas etiquetadas (pasaje correcto o NINGUNO)
src/             preprocesamiento, recuperadores, métricas, asistente y reglas
experimentos/    validación cruzada, ajuste del umbral final y figura
config/          configuración del modelo adoptado (modelo_final.json)
prompts/         plantilla de la etapa generativa (no ejecutada)
resultados/      métricas (JSON), predicciones fuera de pliegue, selección por pliegue, figura
tests/           pruebas unitarias
v0_reglas/       entrega anterior (v0.1): baseline de reglas y 80 casos sintéticos
BITACORA.md      registro de decisiones y resultados
CHANGELOG.md     cambios por versión
```

## Instalación y ejecución

Requiere Python 3.11 o superior.

```bash
pip install -r requirements.txt

# 1. Validación cruzada 10x5 (baseline, ablación, rejilla, pruebas estadísticas) ~30 s
python -m experimentos.validacion_cruzada

# 2. Umbral de derivación del modelo adoptado -> config/modelo_final.json
python -m experimentos.ajustar_modelo_final

# 3. Figura de resultados -> resultados/figuras/validacion_modelos.png
python -m experimentos.graficos

# 4. Consultar al asistente
python -m src.asistente "¿Qué día me entregan la computadora?"

# 5. Pruebas
python -m unittest discover -s tests -t .
```

Todos los resultados se regeneran con la semilla `20260928`.

## Dependencias (versiones usadas)

| Paquete | Versión |
|---|---|
| Python | 3.11.15 |
| numpy | 2.4.4 |
| scipy | 1.17.1 |
| scikit-learn | 1.8.0 |
| nltk (solo el lematizador Snowball para español; no requiere descargas) | 3.9.1 |
| matplotlib | 3.10.9 |

## Metodología de validación

- **Validación cruzada estratificada repetida** (5 pliegues × 10 repeticiones), estratificada por
  tipo de pregunta. En cada pliegue, el umbral de derivación y los hiperparámetros se eligen solo
  con las preguntas de entrenamiento.
- **Baseline (A0):** coincidencia de palabras clave sin normalizar, con umbral de derivación
  ajustado de la misma forma.
- **Ablación (A1–A4)** para medir el aporte de cada ajuste; **A5** elige entre 120 configuraciones
  (TF-IDF de palabras o caracteres y BM25 con k1 ∈ {0.9, 1.2, 1.5, 2.0} y b ∈ {0.5, 0.75, 0.9}).
- **Incertidumbre:** desviación estándar entre pliegues y entre repeticiones, e intervalos de
  confianza del 95 % por bootstrap pareado (5000 remuestreos).
- **Pruebas pareadas:** McNemar exacta (acierto por pregunta) y Wilcoxon (rango recíproco).

## Resultados (media de validación ± DE entre pliegues)

| Variante | Exactitud asistente | Respuesta errónea | Hit@1 | MRR@5 |
|---|---|---|---|---|
| A0 Baseline palabras clave | 0,399 ± 0,059 | 0,475 ± 0,067 | 0,449 | 0,534 |
| A4 BM25 + normalización + títulos (**adoptado**) | 0,644 ± 0,067 | 0,246 ± 0,071 | 0,739 | 0,793 |
| A5 Rejilla de 120 configuraciones | 0,640 ± 0,067 | 0,240 ± 0,060 | 0,718 | 0,781 |

- **A4 frente a A0:** +0,247 de exactitud (IC 95 % bootstrap: 0,160 a 0,333), con McNemar
  p < 0,001 en las 10 repeticiones.
- **A5 frente a A4:** sin diferencia (IC de la diferencia: −0,043 a 0,031; McNemar p ≥ 0,13).
  Se adopta A4, que es más simple y estable.

El detalle completo está en `resultados/metricas_validacion.json`.

## Limitaciones

- El corpus y las preguntas son sintéticos y los escribió el mismo equipo, lo que puede producir
  sesgo de vocabulario.
- La derivación de preguntas fuera del alcance es débil (recall 0,375).
- La etapa generativa todavía no se ha evaluado.

Ver `BITACORA.md`.
