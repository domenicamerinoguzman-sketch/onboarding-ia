"""Evaluación reproducible de un baseline de reglas para onboarding.
Datos sintéticos; no usar como evidencia de desempeño en producción.
"""
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
rng = random.Random(20260925)
rows = []
for i in range(80):
    docs = int(rng.random() < .24)
    equipo = int(rng.random() < .18)
    agenda = int(rng.random() < .20)
    remoto = int(rng.random() < .32)
    acceso = int(remoto and rng.random() < .23)
    aprobacion = int(rng.random() < .11)
    area = ['operaciones', 'ventas', 'tecnologia', 'administracion'][i % 4]
    verdad = int(bool(docs or equipo or agenda or acceso or aprobacion))
    pred = int(bool(docs or equipo or agenda))
    rows.append(dict(id=f'C{i+1:03d}', particion='calibracion' if i < 60 else 'validacion',
                     area=area, documentos_pendientes=docs, equipo_pendiente=equipo,
                     choque_agenda=agenda, modalidad_remota=remoto,
                     acceso_remoto_pendiente=acceso, aprobacion_especial=aprobacion,
                     requiere_intervencion=verdad, prediccion_baseline=pred))

with (ROOT / 'casos_sinteticos.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)

def metrics(part):
    subset = [r for r in rows if r['particion'] == part]
    tp = sum(r['requiere_intervencion'] == r['prediccion_baseline'] == 1 for r in subset)
    tn = sum(r['requiere_intervencion'] == r['prediccion_baseline'] == 0 for r in subset)
    fp = sum(r['requiere_intervencion'] == 0 and r['prediccion_baseline'] == 1 for r in subset)
    fn = sum(r['requiere_intervencion'] == 1 and r['prediccion_baseline'] == 0 for r in subset)
    return dict(n=len(subset), VP=tp, VN=tn, FP=fp, FN=fn,
                exactitud=round((tp+tn)/len(subset), 3),
                precision=round(tp/(tp+fp), 3) if tp+fp else None,
                exhaustividad=round(tp/(tp+fn), 3) if tp+fn else None,
                f1=round(2*tp/(2*tp+fp+fn), 3) if 2*tp+fp+fn else None)

def generar_propuesta(caso):
    """Borrador de agenda y checklist; no envía invitaciones ni crea cuentas."""
    agenda = [
        {'hora': '09:00', 'actividad': 'Bienvenida con talento humano'},
        {'hora': '10:00', 'actividad': 'Políticas y documentación'},
        {'hora': '11:00', 'actividad': f'Inducción de {caso["area"]}'},
        {'hora': '14:00', 'actividad': 'Seguridad y herramientas'},
    ]
    checklist = ['Confirmar documentación', 'Confirmar equipo',
                 'Validar agenda con responsable', f'Inducción de {caso["area"]}']
    if caso['modalidad_remota']:
        checklist.append('Validar acceso remoto')
    return {'id': caso['id'], 'agenda_propuesta': agenda,
            'checklist': checklist,
            'revision_humana': bool(caso['prediccion_baseline'])}

result = {'semilla': 20260925, 'datos': '80 casos sintéticos, sin datos personales',
          'calibracion': metrics('calibracion'), 'validacion': metrics('validacion'),
          'ejemplo_propuesta': generar_propuesta(rows[60])}
(ROOT / 'resultados.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
