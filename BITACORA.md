# Bitácora del proyecto

## 25 de septiembre de 2026 · v0.1 (entrega S5)
- Baseline de tres reglas sobre 80 casos sintéticos: validación VP 10, VN 9, FP 0, FN 1.
- Hallazgo: C075 (aprobación especial) no escalado. Las etiquetas salían del mismo simulador que las reglas: métricas circulares.
- Observación interna: el prototipo no contenía el componente de IA del proyecto aprobado (asistente RAG).

## 28 de septiembre de 2026 · v0.2
**Decisión 1: incorporar el componente de IA.** Se implementa la etapa de recuperación del RAG. La generación con LLM queda especificada (`prompts/respuesta_rag_v1.txt`) pero no se ejecuta, porque el equipo no dispone de acceso a una API de LLM.

**Decisión 2: datos sintéticos.** No hay autorización para usar políticas ni datos reales. Se redactan 46 pasajes ficticios (10 políticas) y 162 preguntas: 46 directas, 92 parafraseadas y 24 fuera del alcance. Las parafraseadas usan vocabulario coloquial a propósito (p. ej. "carnet", "clave", "home office").

**Decisión 3: protocolo de validación.** Se usa validación cruzada estratificada 5 × 10, con el umbral y los hiperparámetros elegidos solo en entrenamiento. Métrica principal: exactitud del asistente (responde con el pasaje correcto o deriva cuando corresponde).

**Resultados (ver `resultados/metricas_validacion.json`)**

| Variante | Exactitud asistente |
|---|---|
| A0 baseline | 0,399 |
| A1 TF-IDF | 0,491 |
| A2 + normalización | 0,561 |
| A3 + títulos | 0,631 |
| A4 BM25 | 0,644 |
| A5 rejilla | 0,640 |

- A4 frente a A0: McNemar p < 0,001 en las 10 repeticiones; IC 95 % de la diferencia: 0,160 a 0,333.
- A5 frente a A4: sin diferencia significativa.
- La rejilla eligió 9 configuraciones distintas en los 50 pliegues (la más frecuente, en 20). Su brecha entre entrenamiento y validación fue mayor: 0,699 frente a 0,640.

**Decisión 4: adoptar A4 (BM25 k1=1,2 y b=0,75, con normalización y títulos).** Tiene el mismo desempeño que A5 con menos configuración y menor variabilidad entre repeticiones (DE 0,007 frente a 0,021). Umbral final: 3,614, en `config/modelo_final.json`.

**Errores observados (A4/A5, predicciones fuera de pliegue)**
1. Sinónimos ausentes del corpus ("carnet", "clave", "quincena", "laptop"): el asistente deriva o recupera un pasaje equivocado.
2. Pasajes vecinos (teletrabajo P36/P37/P38; horario P01/P13): el pasaje correcto suele estar entre los 3 primeros (Hit@3 = 0,848).
3. Preguntas fuera del alcance con palabras comunes ("décimo tercer sueldo" → pago de sueldo): el asistente responde con un pasaje relacionado. Es el principal riesgo de alucinación.

**Reglas de escalamiento v0.2:** se agregan acceso remoto pendiente y aprobación especial, y cada alerta registra su motivo. Ahora cubren los 80 casos sintéticos. Esto es cierto por construcción y no se reporta como mejora estadística.

**Pendientes:**
- Diccionario de sinónimos validado por Talento Humano.
- Recuperación semántica con embeddings multilingües.
- Etapa generativa con verificación de fidelidad.
- Preguntas reales anonimizadas, con autorización.
