"""Figuras de v1.0 (mismo estilo que experimentos/graficos.py).

- resultados/figuras/validacion_v1.png: ablación de v1 en validación cruzada (A4 y B1–B5).
- resultados/figuras/prueba_reservada.png: A0, A4 y v1 en el conjunto reservado, por indicador.

    python -m experimentos.graficos_v1
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

RAIZ = Path(__file__).resolve().parent.parent
TEXTO, TEXTO2, GRIS, AZUL, FONDO, REJILLA = "#0b0b0b", "#52514e", "#9a9994", "#2a78d6", "#ffffff", "#e6e5e0"
coma = matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:.1f}".replace(".", ","))


def estilo(ax):
    ax.set_xlim(0, 1.0)
    ax.xaxis.set_major_formatter(coma)
    ax.grid(axis="x", color=REJILLA, lw=.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.tick_params(colors=TEXTO2, labelsize=8.5, length=0)


def fig_validacion(salida):
    d = json.loads((RAIZ / "resultados" / "v1" / "metricas_validacion_v1.json").read_text(encoding="utf-8"))["modelos"]
    etiquetas = {"A4 BM25 (v0.2)": "A4 BM25 (v0.2)", "B1 A4 + sinónimos": "B1 A4 + sinónimos",
                 "B2 A4 + caracteres": "B2 A4 + caracteres", "B3 sinónimos + caracteres": "B3 Sinónimos + caracteres (v1.0)",
                 "B4 B3 + derivación por cobertura": "B4 B3 + derivación por cobertura",
                 "B5 A4 + derivación por cobertura": "B5 A4 + derivación por cobertura"}
    nombres = list(etiquetas)[::-1]
    paneles = [("exactitud_asistente", "Exactitud del asistente (↑ mejor)"),
               ("respuesta_erronea", "Respuestas erróneas entregadas (↓ mejor)")]
    fig, ejes = plt.subplots(1, 2, figsize=(9.6, 3.5), sharey=True, facecolor=FONDO)
    for ax, (clave, titulo) in zip(ejes, paneles):
        for y, m in enumerate(nombres):
            v = d[m][clave]
            c = AZUL if m.startswith("B3") else GRIS
            ax.plot([v["min_pliegue"], v["max_pliegue"]], [y, y], color=c, lw=1, alpha=.45, solid_capstyle="round")
            ax.plot([v["media"] - v["de_entre_pliegues"], v["media"] + v["de_entre_pliegues"]], [y, y], color=c, lw=3,
                    solid_capstyle="round")
            ax.plot(v["media"], y, "o", ms=8, color=c, mec=FONDO, mew=2, zorder=3)
            ax.text(v["max_pliegue"] + .02, y, f"{v['media']:.2f}".replace(".", ","), va="center", fontsize=8.5, color=TEXTO)
        ax.set_title(titulo, fontsize=10, color=TEXTO, loc="left")
        estilo(ax)
    ejes[0].set_yticks(range(len(nombres)), [etiquetas[m] for m in nombres])
    fig.text(0.01, 0.01, "Validación cruzada 5 × 10 sobre las 162 preguntas de desarrollo. Punto: media; barra gruesa: ±1 DE entre "
             "pliegues; línea fina: mín.–máx.\nLas variantes con sinónimos son optimistas: el diccionario se redactó con los errores de estas preguntas.",
             fontsize=7.2, color=TEXTO2)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(salida / "validacion_v1.png", dpi=220)


def fig_reservada(salida):
    d = json.loads((RAIZ / "resultados" / "v1" / "prueba_final.json").read_text(encoding="utf-8"))["sistemas"]
    etiquetas = {"A0 Baseline palabras clave": "A0 Baseline", "A4 BM25 (v0.2)": "A4 BM25 (v0.2)",
                 "v1 Final (sinónimos + caracteres)": "v1.0 Final"}
    nombres = list(etiquetas)[::-1]
    paneles = [("Exactitud global (↑)", lambda m: m["exactitud_asistente"], lambda m: m["ic95_exactitud"]),
               ("Parafraseadas (↑)", lambda m: m["exactitud_por_tipo"]["parafraseada"], None),
               ("Fuera de alcance: derivación (↑)", lambda m: m["exactitud_por_tipo"]["fuera_alcance"], None),
               ("Respuestas erróneas (↓)", lambda m: m["respuesta_erronea"], lambda m: m["ic95_respuesta_erronea"])]
    fig, ejes = plt.subplots(1, 4, figsize=(10.2, 2.5), sharey=True, facecolor=FONDO)
    for ax, (titulo, valor, ic) in zip(ejes, paneles):
        for y, n in enumerate(nombres):
            m, c = d[n], (AZUL if n.startswith("v1") else GRIS)
            v = valor(m)
            if ic:
                lo, hi = ic(m)
                ax.plot([lo, hi], [y, y], color=c, lw=3, alpha=.55, solid_capstyle="round")
            ax.plot(v, y, "o", ms=8, color=c, mec=FONDO, mew=2, zorder=3)
            ax.text(min(v, 0.80) + .07 if not ic else min(ic(m)[1], 0.86) + .03, y, f"{v:.2f}".replace(".", ","),
                    va="center", fontsize=8.5, color=TEXTO)
        ax.set_title(titulo, fontsize=9.5, color=TEXTO, loc="left")
        estilo(ax)
    ejes[0].set_yticks(range(len(nombres)), [etiquetas[n] for n in nombres])
    fig.text(0.01, 0.01, "Conjunto reservado: 110 preguntas (93 parafraseadas, 17 fuera de alcance) escritas tras congelar el modelo. "
             "Barra: IC 95 % por bootstrap.", fontsize=7.2, color=TEXTO2)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(salida / "prueba_reservada.png", dpi=220)


def main():
    salida = RAIZ / "resultados" / "figuras"
    salida.mkdir(parents=True, exist_ok=True)
    fig_validacion(salida)
    fig_reservada(salida)
    print(salida / "validacion_v1.png", salida / "prueba_reservada.png")


if __name__ == "__main__":
    main()
