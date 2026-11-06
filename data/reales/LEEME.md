# Datos reales de la institución (NO se suben a GitHub)

Esta carpeta recibe los archivos anonimizados del protocolo de validación empírica
(`docs/validacion_empirica/`). Todo lo que se coloque aquí, salvo `plantillas/` y `ejemplo/`,
está excluido por `.gitignore`, porque el repositorio es público.

| Archivo | Quién lo llena | Plantilla |
|---|---|---|
| `hris_extraccion.csv` | Responsable del HRIS (seudónimos y días relativos al ingreso) | `plantillas/hris_extraccion.csv` |
| `bitacora_tiempos.csv` | Los 3 analistas, durante dos semanas | `plantillas/bitacora_tiempos.csv` |
| `sesiones_analistas.csv` | Observador de las sesiones cronometradas | `plantillas/sesiones_analistas.csv` |
| `cuestionario_usuarios.csv` | Participantes (SUS y satisfacción) | `plantillas/cuestionario_usuarios.csv` |
| `tareas_usabilidad.csv` | Observador de la prueba de usabilidad | `plantillas/tareas_usabilidad.csv` |

Se pueden llenar en Excel y guardar como CSV (coma o punto y coma). Para ver el formato con datos
inventados: `data/reales/ejemplo/` (SINTÉTICO, no son resultados).

```bash
python -m experimentos.linea_base_real
python -m experimentos.analizar_estudio_usuarios --reevaluar
```

Los resultados agregados se escriben en `resultados/validacion_empirica/`, que tampoco se sube
salvo que la institución lo autorice.
