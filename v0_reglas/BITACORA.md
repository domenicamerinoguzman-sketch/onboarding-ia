# Bitácora de evaluación preliminar

## 25 de septiembre de 2026

- Se implementó un prototipo local que propone cuatro bloques de inducción y un checklist de incorporación por área y modalidad.
- Se definió un baseline de tres reglas y un conjunto fijo de 80 casos sintéticos. Se reservaron 60 para calibración y 20 para validación.
- Se ejecutó `python baseline_onboarding.py`; se generaron `casos_sinteticos.csv` y `resultados.json`.
- Validación: VP 10, VN 9, FP 0, FN 1; exactitud 0,950, precisión 1,000, exhaustividad 0,909 y F1 0,952.
- Se identificó el caso C075: aprobación especial no contemplada en el baseline. La generación actual tampoco comprueba disponibilidad real ni horarios de los participantes.
- Pendiente: revisión de etiquetas con talento humano, piloto con datos autorizados y prueba de calendario antes de automatizar envíos.

Este registro documenta archivos locales listos para incorporar al repositorio del proyecto. No consta aquí una actualización de un repositorio remoto.
