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

## 26 de octubre de 2026 · v1.0 (avance consolidado)

**Decisión 5: atacar los tres errores de v0.2 con cambios medibles.** Se prueban, con las mismas 50
particiones y el mismo protocolo: B1 diccionario de sinónimos, B2 n-gramas de caracteres, B3 ambos,
B4 B3 + derivación por cobertura y B5 A4 + cobertura (ver `resultados/v1/metricas_validacion_v1.json`).

| Variante | Exactitud (CV) | Respuesta errónea |
|---|---|---|
| A4 (v0.2) | 0,644 | 0,246 |
| B1 + sinónimos | 0,807 | 0,157 |
| B2 + caracteres | 0,696 | 0,213 |
| B3 sinónimos + caracteres | 0,831 | 0,151 |
| B4 B3 + cobertura | 0,832 | 0,140 |
| B5 A4 + cobertura | 0,650 | 0,209 |

**Advertencia registrada antes de la prueba final:** el diccionario se redactó con los errores de v0.2
sobre estas mismas preguntas, por lo que la mejora de B1/B3/B4 es optimista.

**Decisión 6: adoptar B3.** B4 no difiere de B3 (IC de la diferencia −0,037 a 0,012) y la cobertura se
fijó en 0 en 45 de 50 pliegues. Umbral final 4,563 (`config/modelo_final.json`). Se congela el modelo
(commit `v1.0 (1/5)`).

**Decisión 7: conjunto de prueba reservado.** Después de congelar el modelo se redactan 110 preguntas
nuevas (93 parafraseadas, 17 fuera de alcance; commit `v1.0 (2/5)`). No se usan para ninguna decisión.

**Resultado de la prueba final (`resultados/v1/prueba_final.json`)**

| Sistema | Exactitud | Respuesta errónea | Hit@1 | Fuera de alcance |
|---|---|---|---|---|
| A0 | 0,509 | 0,427 | 0,591 | 0,235 |
| A4 | 0,773 | 0,173 | 0,785 | 0,765 |
| v1.0 | 0,773 | 0,164 | 0,828 | 0,529 |

- v1.0 = A4 en exactitud (McNemar p = 1; 4 aciertos exclusivos de cada uno). **La mejora de la
  validación cruzada no se sostuvo.** v1.0 recupera mejor (más útil para el LLM, que recibe 3 pasajes)
  pero deriva peor: los n-gramas de caracteres elevan el puntaje de preguntas ajenas al corpus.
- No se reajusta nada con el conjunto reservado; hacerlo lo invalidaría como prueba.
- A4 obtiene 0,773 en el reservado frente a 0,644 en CV: el conjunto reservado parece más fácil
  (lo redactó el mismo equipo, que conoce el vocabulario del corpus). Limitación declarada.

**Decisión 8: generación dual con verificación.** Sin API comercial, se usa un LLM abierto local
(Ollama) para no enviar datos a terceros. Toda respuesta del LLM pasa un verificador (cita recuperada +
cifras presentes en el pasaje); si falla, se entrega el respaldo extractivo. La ruta del LLM se probó con
un servidor simulado; **la evaluación con el modelo real queda pendiente** (`evaluar_generacion --modo llm_local`).

**Decisión 9: flujos como automatización tradicional.** 13 tareas del modelo AS-IS preliminar: 9 se
automatizan, 1 la atiende el asistente de IA, 3 siguen siendo humanas (validar documentos, contrato
asistido y asignar compañero guía). Conectores simulados con la interfaz de una integración REST.

**Robustez y seguridad.** Tildes y mayúsculas no afectan; con dos erratas por pregunta v1.0 cae a 0,615
(A4: 0,576). Guardas: 12/14 ataques detectados en la primera ejecución, 0/8 falsos positivos; S02 y S13
se corrigieron después (la cifra posterior, 14/14, no es independiente). Datos personales: 6/6.

**Pendientes:**
- Evaluar la generación con el LLM real y completar la revisión humana de 30 respuestas.
- Tratar la derivación como un problema propio (p. ej. clasificador de alcance o verificación del LLM),
  con un nuevo conjunto de desarrollo y otro reservado.
- Validar con Talento Humano el diccionario de sinónimos, el AS-IS y la línea base.
