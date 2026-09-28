"""Figura de la validación cruzada: media y variabilidad entre pliegues por variante.

    python -m experimentos.graficos
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

RAIZ = Path(__file__).resolve().parent.parent
TEXTO, TEXTO2, GRIS, AZUL, FONDO = "#0b0b0b", "#52514e", "#9a9994", "#2a78d6", "#ffffff"
ETIQUETAS = {
    "A0 Baseline palabras clave": "A0 Baseline (palabras clave)",
    "A1 TF-IDF sin preprocesar": "A1 TF-IDF sin preprocesar",
    "A2 + normalización (vacías, raíces)": "A2 + normalización",
    "A3 + títulos en el índice": "A3 + títulos en el índice",
    "A4 BM25 por defecto": "A4 BM25 (modelo adoptado)",
    "A5 Ajustado (rejilla de 120 configuraciones)": "A5 Rejilla de 120 config.",
}


def main():
    d = json.loads((RAIZ / "resultados" / "metricas_validacion.json").read_text(encoding="utf-8"))["modelos"]
    nombres = list(d)[::-1]
    paneles = [("exactitud_asistente", "Exactitud del asistente (↑ mejor)"),
               ("respuesta_erronea", "Respuestas erróneas entregadas (↓ mejor)")]
    fig, ejes = plt.subplots(1, 2, figsize=(9.2, 3.4), sharey=True, facecolor=FONDO)
    for ax, (clave, titulo) in zip(ejes, paneles):
        for y, m in enumerate(nombres):
            v = d[m][clave]
            color = AZUL if m.startswith("A4") else GRIS
            ax.plot([v["min_pliegue"], v["max_pliegue"]], [y, y], color=color, lw=1, alpha=.45,
                    solid_capstyle="round")
            ax.plot([v["media"] - v["de_entre_pliegues"], v["media"] + v["de_entre_pliegues"]], [y, y],
                    color=color, lw=3, solid_capstyle="round")
            ax.plot(v["media"], y, "o", ms=8, color=color, mec=FONDO, mew=2, zorder=3)
            ax.text(v["max_pliegue"] + .02, y, f"{v['media']:.2f}".replace(".", ","), va="center",
                    fontsize=8.5, color=TEXTO)
        ax.set_title(titulo, fontsize=10, color=TEXTO, loc="left")
        ax.set_xlim(0, 1.0)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:.1f}".replace(".", ",")))
        ax.grid(axis="x", color="#e6e5e0", lw=.8)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
        ax.tick_params(colors=TEXTO2, labelsize=8.5, length=0)
    ejes[0].set_yticks(range(len(nombres)), [ETIQUETAS[m] for m in nombres])
    fig.text(0.01, 0.01, "Punto: media de 10 repeticiones × 5 pliegues. Barra gruesa: ±1 DE entre pliegues. "
             "Línea fina: mínimo–máximo entre los 50 pliegues.", fontsize=7.5, color=TEXTO2)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    salida = RAIZ / "resultados" / "figuras"
    salida.mkdir(parents=True, exist_ok=True)
    fig.savefig(salida / "validacion_modelos.png", dpi=220)
    print(salida / "validacion_modelos.png")


if __name__ == "__main__":
    main()
