"""Métricas del asistente de recuperación y selección del umbral de derivación.

Definiciones (clase de interés: preguntas del colaborador):
- exactitud_asistente: proporción de preguntas bien resueltas. Una pregunta dentro del
  alcance está bien resuelta si el asistente responde (no deriva) con el pasaje correcto;
  una fuera del alcance, si el asistente deriva a Talento Humano.
- respuesta_erronea: proporción de preguntas en las que el asistente entrega un pasaje
  equivocado (dentro del alcance) o responde algo que no está en las políticas (fuera del
  alcance). Es el indicador de riesgo de alucinación de la etapa de recuperación.
- hit@1, hit@3, MRR@5: calidad de recuperación en preguntas dentro del alcance, sin umbral.
- precision/recall de derivación: clase positiva = pregunta fuera del alcance.

v1.0: la derivación puede usar dos señales, el puntaje del primer pasaje (umbral u) y la
cobertura de la consulta por ese pasaje (umbral c). Ambos se eligen solo con entrenamiento.
"""
import numpy as np

K_MRR = 5


def desempatar(matriz: np.ndarray, semilla: int = 0) -> np.ndarray:
    """Rompe empates con ruido ínfimo reproducible, para no favorecer el orden del corpus."""
    rng = np.random.default_rng(semilla)
    return matriz + rng.uniform(0, 1e-9, size=matriz.shape)


def resumen_por_pregunta(matriz: np.ndarray, oro: np.ndarray, cobertura: np.ndarray | None = None) -> dict:
    """oro[i] = índice del pasaje correcto, o -1 si la pregunta está fuera del alcance.

    cobertura[i] = cobertura de la pregunta i por su primer pasaje (opcional).
    """
    top1 = matriz.argmax(axis=1)
    puntaje_top1 = matriz.max(axis=1)
    rango = np.full(len(oro), np.inf)
    dentro = oro >= 0
    orden = np.argsort(-matriz, axis=1)
    for i in np.where(dentro)[0]:
        rango[i] = int(np.where(orden[i] == oro[i])[0][0]) + 1
    if cobertura is None:
        cobertura = np.ones(len(oro))
    return dict(top1=top1, puntaje_top1=puntaje_top1, rango=rango, dentro=dentro, oro=oro,
                cobertura=np.asarray(cobertura, float))


def decisiones(res: dict, umbral: float, idx: np.ndarray, umbral_cobertura: float = 0.0) -> dict:
    deriva = (res["puntaje_top1"][idx] < umbral) | (res["cobertura"][idx] < umbral_cobertura)
    dentro = res["dentro"][idx]
    acierto_top1 = res["top1"][idx] == res["oro"][idx]
    correcta = np.where(dentro, (~deriva) & acierto_top1, deriva)
    erronea = np.where(dentro, (~deriva) & ~acierto_top1, ~deriva)
    rr = np.where(res["rango"][idx] <= K_MRR, 1.0 / res["rango"][idx], 0.0)
    return dict(correcta=correcta, erronea=erronea, deriva=deriva, dentro=dentro,
                hit1=res["rango"][idx] <= 1, hit3=res["rango"][idx] <= 3, rr=rr)


def metricas(d: dict) -> dict:
    dentro, fuera = d["dentro"], ~d["dentro"]
    vp = int((d["deriva"] & fuera).sum())
    pred_pos = int(d["deriva"].sum())
    return dict(
        exactitud_asistente=float(d["correcta"].mean()),
        respuesta_erronea=float(d["erronea"].mean()),
        hit1=float(d["hit1"][dentro].mean()),
        hit3=float(d["hit3"][dentro].mean()),
        mrr5=float(d["rr"][dentro].mean()),
        precision_derivacion=vp / pred_pos if pred_pos else float("nan"),
        recall_derivacion=vp / int(fuera.sum()) if fuera.sum() else float("nan"),
    )


def elegir_umbral(res: dict, idx: np.ndarray) -> float:
    """Umbral que maximiza exactitud_asistente en el conjunto de entrenamiento (empate: el menor)."""
    candidatos = np.unique(np.concatenate([[-np.inf], res["puntaje_top1"][idx]]))
    mejor, mejor_valor = -np.inf, -1.0
    for u in candidatos:
        v = decisiones(res, u, idx)["correcta"].mean()
        if v > mejor_valor + 1e-12:
            mejor, mejor_valor = u, v
    return float(mejor)


UMBRALES_COBERTURA = np.round(np.arange(0.0, 0.951, 0.05), 2)


def elegir_reglas(res: dict, idx: np.ndarray) -> tuple[float, float]:
    """(umbral de puntaje, umbral de cobertura) que maximizan exactitud en entrenamiento.

    Desempate: menor tasa de respuesta errónea y luego los umbrales más bajos (más cobertura).
    """
    candidatos = np.unique(np.concatenate([[-np.inf], res["puntaje_top1"][idx]]))
    mejor, clave_mejor = (-np.inf, 0.0), None
    for c in UMBRALES_COBERTURA:
        for u in candidatos:
            d = decisiones(res, u, idx, c)
            clave = (round(d["correcta"].mean(), 12), -round(d["erronea"].mean(), 12))
            if clave_mejor is None or clave > clave_mejor:
                mejor, clave_mejor = (float(u), float(c)), clave
    return mejor
