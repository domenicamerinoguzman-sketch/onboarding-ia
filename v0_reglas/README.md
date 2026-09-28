# Prototipo mínimo de onboarding

Evaluación académica reproducible con datos **sintéticos**. No contiene datos personales, integra calendarios ni crea cuentas. La agenda y el checklist son propuestas que requieren revisión humana antes de ejecutarse.

## Ejecutar

```bash
python baseline_onboarding.py
```

El script usa únicamente la biblioteca estándar de Python y vuelve a generar `casos_sinteticos.csv` y `resultados.json` con la semilla `20260925`.

## Lógica

- Entrada: área, modalidad y cinco indicadores binarios de pendientes o conflictos.
- Baseline: `requiere_intervencion = documentos_pendientes OR equipo_pendiente OR choque_agenda`.
- Referencia sintética: añade `acceso_remoto_pendiente OR aprobacion_especial` a los tres indicadores anteriores. Se construye para ensayar el pipeline; **no es una etiqueta validada por talento humano**.
- Salida: clasificación para revisión, cuatro bloques de agenda y checklist común con paso remoto condicional.
- Calibración: C001–C060. Validación: C061–C080, separada por identificador. Las reglas fueron definidas previamente; no hay entrenamiento estadístico.

## Métricas

`resultados.json` registra VP, VN, FP, FN, exactitud, precisión, exhaustividad y F1 de la clase “requiere intervención”. El resultado de validación es 19/20 aciertos, con un falso negativo por aprobación especial (C075). La muestra pequeña y construida con la misma lógica impide extrapolar el resultado a producción.

## Próxima validación

Con autorización institucional, sustituir los casos simulados por registros anonimizados y etiquetas revisadas por talento humano. Separar por cohorte temporal; medir exhaustividad de excepciones, conflictos de agenda, completitud del checklist, tiempo de preparación y correcciones manuales. Documentar consentimiento, minimización de datos y control de acceso.
