# Rúbrica de revisión humana de respuestas

Complementa al verificador automático (`src/guardas.py`), que solo comprueba la cita y las cifras.
`experimentos/evaluar_generacion.py` genera dos copias de la misma muestra aleatoria de 30 respuestas del
conjunto reservado (semilla 20260928): `resultados/v1/revision_humana_<etiqueta>_revisor1.csv` y `_revisor2.csv`.
Cada revisor llena la suya sin consultar al otro (se puede abrir y guardar en Excel; se acepta coma o
punto y coma). Después:

```bash
python -m experimentos.analizar_revision_humana --etiqueta llm_local_qwen2.5_3b
```

calcula el acuerdo (kappa de Cohen) y lista los desacuerdos. Se discuten, se guarda el resultado como
`revision_humana_<etiqueta>_consenso.csv` y se vuelve a ejecutar para el resultado final.

**Revisores:** al menos dos integrantes del equipo, de forma independiente; idealmente, un analista
de Talento Humano. Se reporta el acuerdo entre revisores (porcentaje de acuerdo y kappa de Cohen).

| Columna | Pregunta | Valores |
|---|---|---|
| `revision_correcta` | ¿La acción es la adecuada? (responder con el pasaje correcto o derivar si la pregunta está fuera de alcance) | 1 = sí · 0 = no |
| `revision_fiel` | ¿Toda afirmación de la respuesta está respaldada por el pasaje citado? (no solo las cifras) | 1 = sí · 0 = no · NA si derivó |
| `revision_util` | ¿La respuesta resuelve la duda de un nuevo colaborador sin necesidad de leer la política completa? | 1 a 5 (Likert) |
| `revision_comentario` | Error observado: pasaje equivocado, omisión, afirmación no respaldada, tono, otro | texto libre |

**Indicadores derivados**
- Tasa de alucinación (humana) = respuestas con `revision_fiel = 0` / respuestas entregadas.
- Utilidad media y proporción de respuestas con utilidad ≥ 4.
- Diferencia entre la fidelidad automática y la humana: estima cuánto deja pasar el verificador.

Ningún resultado de esta rúbrica se reporta hasta que la revisión se haya hecho.
