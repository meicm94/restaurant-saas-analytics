"""
Estilo comun de los graficos del proyecto.

Paleta categorica validada para daltonismo (deuteranopia, protanopia,
tritanopia) sobre fondo claro: se usan las tres primeras ranuras para series
independientes y la rampa azul para escalas continuas (mapas de calor).
Los colores nunca son la unica codificacion: siempre hay leyenda o etiqueta.
"""
import matplotlib as mpl
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e3e2de"

# categoricos (orden fijo, nunca ciclado)
BLUE, ORANGE, AQUA, YELLOW, RED = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e34948"
CAT = [BLUE, ORANGE, AQUA]
# rampa secuencial azul claro -> oscuro (magnitud continua)
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281"]

mpl.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 10,
    "axes.labelcolor": INK_SOFT,
    "axes.edgecolor": GRID,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.7,
    "text.color": INK,
    "xtick.color": INK_SOFT,
    "ytick.color": INK_SOFT,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "figure.dpi": 130,
})


def despine(ax, left=False):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if left:
        ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", visible=False)


def title(ax, headline, sub=None):
    """Titular en negro y subtitulo en gris, ambos alineados a la izquierda."""
    ax.text(0, 1.11 if sub else 1.03, headline, transform=ax.transAxes,
            fontsize=11, fontweight="bold", color=INK, va="bottom")
    if sub:
        ax.text(0, 1.03, sub, transform=ax.transAxes, fontsize=8.5,
                color=INK_SOFT, va="bottom")


def save(fig, path):
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"  figura -> {path.name}")
