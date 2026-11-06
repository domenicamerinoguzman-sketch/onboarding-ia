"""Genera datos de EJEMPLO SINTÉTICOS con el formato de las plantillas de validación empírica.

Sirven para probar los scripts de análisis y para ver cómo se llenan los archivos. NO son
resultados y no deben citarse como tales. Se escriben en data/reales/ejemplo/.

    python -m experimentos.generar_ejemplo_validacion
"""
import csv
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "reales" / "ejemplo"
PLANTILLAS = RAIZ / "data" / "reales" / "plantillas"
# minutos típicos INVENTADOS por actividad (manual) para el ejemplo
MIN_EJEMPLO = {"T01": 15, "T02": 20, "T03": 10, "T04": 45, "T05": 40, "T06": 12, "T07": 8, "T08": 10,
               "T09": 15, "T10": 10, "T11": 10, "T12": 25, "T13": 20, "T99": 5}
MEDIDAS = ["T02", "T03", "T06", "T07", "T08", "T09", "T11", "T12", "T13"]


def campos(nombre):
    return (PLANTILLAS / nombre).read_text(encoding="utf-8").strip().split(",")


def escribir(nombre, filas):
    with (DESTINO / nombre).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos(nombre))
        w.writeheader()
        w.writerows(filas)


def main():
    rng = random.Random(7)
    DESTINO.mkdir(parents=True, exist_ok=True)
    meses = [f"2025-{m:02d}" for m in (11, 12)] + [f"2026-{m:02d}" for m in range(1, 11)]
    hris, n = [], 0
    for mes in meses:
        for _ in range(rng.randint(22, 36)):
            n += 1
            hris.append(dict(id_caso=f"C{n:04d}", mes_ingreso=mes, analista=rng.choice(["A1", "A2", "A3"]),
                             area_grupo=rng.choice(["Negocios", "Operaciones", "Tecnología", "Soporte"]),
                             modalidad=rng.choices(["presencial", "remota"], [0.8, 0.2])[0],
                             dias_solicitud_a_ingreso=rng.randint(10, 45), dias_documentos_completos=rng.randint(-10, 2),
                             dias_contrato_firmado=rng.choice([-1, 0, 0, 0, 1]), dias_usuario_red=rng.randint(-2, 3),
                             dias_correo=rng.randint(-2, 3), dias_equipo_entregado=rng.randint(2, 8) if rng.random() < 0.8 else "",
                             documentos_rechazados=rng.choices([0, 1, 2], [0.7, 0.2, 0.1])[0],
                             reprogramado=int(rng.random() < 0.08), observacion="EJEMPLO SINTÉTICO"))
    escribir("hris_extraccion.csv", hris)

    bit = []
    for c in range(1, 16):
        caso, an = f"B{c:03d}", rng.choice(["A1", "A2", "A3"])
        acts = [a for a in MIN_EJEMPLO if a not in ("T07",) or rng.random() < 0.2]
        for k, a in enumerate(acts):
            bit.append(dict(id_caso=caso, analista=an, fecha=f"2026-11-{rng.randint(9, 20):02d}", actividad=a,
                            minutos=max(1, round(rng.gauss(MIN_EJEMPLO[a], MIN_EJEMPLO[a] * 0.3))),
                            registro_completo=int(k == len(acts) - 1), comentario="EJEMPLO SINTÉTICO"))
    escribir("bitacora_tiempos.csv", bit)

    ses = []
    for an, orden in (("A1", "AB"), ("A2", "BA"), ("A3", "AB")):
        for conj, casos in (("A", ["S1", "S2", "S3", "S4"]), ("B", ["S5", "S6", "S7", "S8"])):
            cond = "manual" if (orden == "AB") == (conj == "A") else "prototipo"
            for caso in casos:
                for t in MEDIDAS:
                    base = MIN_EJEMPLO[t] * rng.uniform(0.8, 1.2)
                    m = base if cond == "manual" else base * rng.uniform(0.25, 0.55)
                    ses.append(dict(analista=an, orden=orden, caso=caso, condicion=cond, tarea=t, minutos=round(m, 1),
                                    errores=rng.choices([0, 1], [0.85, 0.15] if cond == "manual" else [0.95, 0.05])[0],
                                    completada=1, observacion="EJEMPLO SINTÉTICO"))
    escribir("sesiones_analistas.csv", ses)

    cue = []
    for i in range(1, 14):
        perfil = "analista_th" if i <= 3 else "colaborador_nuevo"
        fila = dict(participante=f"P{i:02d}", perfil=perfil, fecha="2026-11-25", comentario="EJEMPLO SINTÉTICO")
        for k in range(1, 11):
            fila[f"sus{k}"] = rng.choice([4, 5, 4]) if k % 2 else rng.choice([1, 2, 2])
        fila.update(satisfaccion_general=rng.choices([3, 4, 5], [0.15, 0.45, 0.4])[0],
                    utilidad_respuestas=rng.choice([3, 4, 5]), confianza_respuestas=rng.choice([3, 4, 4, 5]),
                    recomendaria=rng.choice([4, 5]))
        cue.append(fila)
    escribir("cuestionario_usuarios.csv", cue)

    esc = [r for r in csv.DictReader((RAIZ / "validacion" / "escenarios_usabilidad.csv").open(encoding="utf-8"))]
    tar = []
    for i in range(4, 14):
        for e in esc:
            acierta = rng.random() < 0.75
            tar.append(dict(participante=f"P{i:02d}", escenario=e["escenario"], pregunta_escrita="",
                            accion_asistente=("derivar" if e["pasaje_esperado"] == "NINGUNO" else "responder") if acierta else "responder",
                            pasaje_mostrado=(e["pasaje_esperado"] if e["pasaje_esperado"] != "NINGUNO" else "") if acierta else "P14",
                            exito=int(acierta or rng.random() < 0.3), segundos=rng.randint(25, 150),
                            ayuda=int(rng.random() < 0.1), observacion="EJEMPLO SINTÉTICO"))
    escribir("tareas_usabilidad.csv", tar)
    (DESTINO / "LEEME.txt").write_text("DATOS DE EJEMPLO SINTÉTICOS generados por experimentos/generar_ejemplo_validacion.py.\n"
                                       "Solo muestran el formato. NO son resultados.\n", encoding="utf-8")
    print(f"Ejemplos escritos en {DESTINO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
