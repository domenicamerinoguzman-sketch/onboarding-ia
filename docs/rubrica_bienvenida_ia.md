# Rúbrica de revisión: correo de bienvenida redactado por IA

Segundo componente de IA del prototipo (`src/bienvenida_ia.py`, prompt `prompts/bienvenida_v1.txt`).
El LLM local redacta un borrador personalizado; una guarda determinista lo revisa (cifras que no están
en los datos, enlaces, nombre, fechas, longitud) y, si falla, se usa la plantilla. En el sistema,
**Talento Humano siempre edita y aprueba** el correo antes de enviarlo; el sistema registra qué
proporción del texto cambió el analista.

## Procedimiento

1. Con Ollama abierto y el modelo descargado: doble clic en `EVALUAR_BIENVENIDA_WINDOWS.bat`
   (o `python -m experimentos.evaluar_bienvenida generar --modo llm_local`).
   Genera 22 borradores (S1–S8 y C-DEMO-01..03, cada uno con documentos pendientes y con el expediente
   completo) y dos planillas: `resultados/v1/revision_bienvenida_<etiqueta>_revisor1.csv` y `_revisor2.csv`.
2. Dos integrantes (idealmente uno de Talento Humano) llenan su planilla **por separado**. Se abre en
   Excel; columna `datos_del_ingreso` = lo que recibió el modelo; columna `correo` = el borrador.
3. `python -m experimentos.evaluar_bienvenida analizar --etiqueta <etiqueta>` calcula los indicadores
   y el acuerdo entre revisores (kappa).

| Columna | Pregunta | Valores |
|---|---|---|
| `rev_datos_correctos` | ¿Todos los datos del correo (nombre, cargo, área, fechas, documentos, plazo) coinciden con `datos_del_ingreso`? | 1 = sí · 0 = no |
| `rev_afirmacion_inventada` | ¿Afirma algo que no está en los datos (un beneficio, una persona, un horario, una política)? | 1 = sí · 0 = no |
| `rev_personalizacion` | ¿Se nota escrito para esta persona (cargo, área, modalidad, pendientes)? | 1 a 5 |
| `rev_tono` | ¿El tono es cálido y profesional, adecuado para una institución financiera? | 1 a 5 |
| `rev_enviaria` | Como analista, ¿lo enviaría? | 2 = sin cambios · 1 = con cambios menores (menos de 5 minutos) · 0 = no, lo reescribiría |
| `rev_comentario` | Qué cambiaría o qué está mal | texto libre |

Las filas con `origen = plantilla` son borradores que la guarda descartó (o casos sin LLM): se
cuentan como descartes y no entran en los indicadores de calidad de la IA.

## Criterios (propuestos el 6 de noviembre de 2026, antes de generar los borradores)

El grupo los confirma antes de ejecutar el paso 1; cualquier cambio posterior se registra en
`BITACORA.md` con su justificación.

| Indicador | Criterio | Por qué |
|---|---|---|
| Borradores con afirmación inventada (basta que un revisor la marque) | 0 | Un dato inventado en un correo oficial es el riesgo principal. |
| Borradores con todos los datos correctos | ≥ 95 % | Los datos los copia el modelo de una lista; deben coincidir. |
| Enviables sin cambios o con cambios menores (ambos revisores ≥ 1) | ≥ 80 % | Mide si el borrador ahorra trabajo al analista. |
| Personalización media | ≥ 4 de 5 | Es la razón para usar IA en lugar de la plantilla. |

Si no se cumplen, la funcionalidad se mantiene solo con revisión humana obligatoria (como ya
funciona) y se reporta así; no se presenta como automatización de la comunicación.
Ningún resultado se reporta antes de completar la revisión.
