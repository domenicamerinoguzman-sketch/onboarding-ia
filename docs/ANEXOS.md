# Índice de anexos técnicos y evidencias

| Anexo | Contenido | Ubicación |
|---|---|---|
| A. Prototipo v0.1 | Baseline de reglas, 80 casos sintéticos, métricas | `v0_reglas/` |
| B. Validación v0.2 | Validación cruzada 5 × 10 (A0–A5), pruebas pareadas, selección por pliegue | `resultados/metricas_validacion.json`, `resultados/seleccion_por_pliegue.csv`, `resultados/predicciones_fuera_de_pliegue_rep0.csv`, `resultados/figuras/validacion_modelos.png` |
| C. Validación v1.0 | Ablación A4, B1–B5 con las mismas particiones | `resultados/v1/metricas_validacion_v1.json`, `resultados/v1/predicciones_fuera_de_pliegue_v1_rep0.csv`, `resultados/figuras/validacion_v1.png` |
| D. Prueba final | Conjunto reservado: métricas, IC, McNemar, predicciones por pregunta | `resultados/v1/prueba_final.json`, `resultados/v1/prueba_final_predicciones.csv`, `resultados/figuras/prueba_reservada.png` |
| E. Robustez y seguridad | Perturbaciones, guardas de entrada, verificador | `resultados/v1/robustez.json`, `data/pruebas_seguridad.csv` |
| F. Extremo a extremo | Modo extractivo; plantilla para LLM local y revisión humana | `resultados/v1/generacion_extractivo*.{json,csv}`, `resultados/v1/revision_humana_extractivo.csv`, `docs/rubrica_revision_humana.md` |
| G. Prompts | v1 (no ejecutado) y v2 (vigente) | `prompts/` |
| H. Interpretabilidad | Descomposición exacta de BM25 por término (en cada respuesta: `trazabilidad.terminos_top1`) | `src/recuperadores.py` (`contribuciones`) |
| I. Flujos | Definición TO-BE, plantillas, casos de demostración | `config/flujo_onboarding.json`, `plantillas/`, `data/casos_demo.json` |
| J. Demo | Capturas de la demo web | `docs/img/demo_*.png` |
| K. Arquitectura | Diagrama (fuente Mermaid y PNG) | `docs/arquitectura.mmd`, `docs/img/arquitectura_v1.png` |
| L. Pruebas | 35 pruebas unitarias y de integración | `tests/` |
| M. Decisiones | Bitácora y registro de cambios | `BITACORA.md`, `CHANGELOG.md` |

Entregables anteriores del curso (estado del arte, diseño de la solución, informe de resultados
preliminares, informe de ajustes, reporte de interpretabilidad y ética) se resumen en el documento
final y no se duplican en el repositorio.
