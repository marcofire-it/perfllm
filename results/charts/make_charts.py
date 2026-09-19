"""Generates the round-1 comparison charts (PNG). Usage: python results/charts/make_charts.py"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

# --- data (from results/LEADERBOARD.md and the scorecards) ---------------------
MODELS = ["Claude Sonnet 5", "Claude Opus 4.6", "Qwen 3.8 27B (Q6)"]
TASKS = ["Task 1: log analyzer\n(easy)", "Task 2: DAG runner\n(medium)", "Task 3: interpreter\n(hard)"]
SCORES = {  # per task, 0-100
    "Claude Sonnet 5": [93, 96, 95],
    "Claude Opus 4.6": [88, 96, 92],
    "Qwen 3.8 27B (Q6)":    [97, 91, 81],
}
WEIGHTED = {"Claude Sonnet 5": 95.0, "Claude Opus 4.6": 92.7, "Qwen 3.8 27B (Q6)": 87.0}
# points lost per section, summed over the 3 tasks (max A 165, B 45, C 45, D 30, E 15)
LOST = {  # A, B, C, D, E
    "Claude Sonnet 5": [0, 2, 6, 8, 0],
    "Claude Opus 4.6": [0, 2, 9, 13, 0],
    "Qwen 3.8 27B (Q6)":    [1, 6, 14, 8, 2],
}
SECTIONS = ["A: hidden tests", "B: spec adherence", "C: code quality", "D: robustness", "E: notes & own tests"]

# --- palette (validated reference palette, light mode) -------------------------
SURFACE = "#fcfcfb"
TEXT, TEXT2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8985", "#e6e5e1"
MODEL_COLOR = dict(zip(MODELS, ["#2a78d6", "#eb6834", "#1baf7a"]))
SECTION_COLOR = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": TEXT2, "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def title(fig, text, sub):
    fig.text(0.04, 0.955, text, fontsize=16, weight="bold", color=TEXT, ha="left", va="top")
    fig.text(0.04, 0.905, sub, fontsize=11, color=TEXT2, ha="left", va="top")


# --- chart 1: final weighted score ---------------------------------------------
fig, ax = plt.subplots(figsize=(9, 4.2), dpi=200)
fig.subplots_adjust(left=0.24, right=0.96, top=0.78, bottom=0.14)
order = sorted(MODELS, key=lambda m: WEIGHTED[m])
for i, m in enumerate(order):
    v = WEIGHTED[m]
    ax.barh(i, v, height=0.5, color=MODEL_COLOR[m], linewidth=0)
    ax.text(v + 0.8, i, f"{v:.1f}", va="center", ha="left", color=TEXT, fontsize=13, weight="bold")
ax.set_yticks(range(len(order)), order, color=TEXT)
ax.set_xlim(0, 100)
ax.set_xlabel("Weighted score (0-100)")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", length=0)
title(fig, "Overall score, round 1",
      "Weighted 1:2:3 by task difficulty. 55 pts from hidden tests, 45 from manual review.")
fig.savefig(OUT / "1_overall_score.png")
plt.close(fig)

# --- chart 2: score per task, grouped bars -------------------------------------
fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
fig.subplots_adjust(left=0.08, right=0.97, top=0.78, bottom=0.18)
n = len(MODELS)
w = 0.24
gap = 0.02
for j, m in enumerate(MODELS):
    xs = [i + (j - (n - 1) / 2) * (w + gap) for i in range(len(TASKS))]
    vals = SCORES[m]
    ax.bar(xs, vals, width=w, color=MODEL_COLOR[m], linewidth=0, label=m)
    for x, v in zip(xs, vals):
        ax.text(x, v + 1.2, str(v), ha="center", va="bottom", color=TEXT, fontsize=11)
ax.set_xticks(range(len(TASKS)), TASKS, color=TEXT)
ax.set_ylim(0, 105)
ax.set_ylabel("Score (0-100)")
ax.grid(axis="x", visible=False)
ax.tick_params(axis="x", length=0)
ax.legend(loc="lower left", frameon=False, ncol=3, bbox_to_anchor=(0, 1.0), fontsize=11, labelcolor=TEXT)
title(fig, "Score per task",
      "All three passed 98-100% of the hidden tests; the spread comes from the manual review.")
fig.savefig(OUT / "2_score_per_task.png")
plt.close(fig)

# --- chart 3: points lost per section (stacked, horizontal) --------------------
fig, ax = plt.subplots(figsize=(10, 4.4), dpi=200)
fig.subplots_adjust(left=0.20, right=0.97, top=0.74, bottom=0.16)
order = sorted(MODELS, key=lambda m: -sum(LOST[m]))
for i, m in enumerate(order):
    left = 0.0
    for k, (sec, col) in enumerate(zip(SECTIONS, SECTION_COLOR)):
        v = LOST[m][k]
        if v == 0:
            continue
        ax.barh(i, v, left=left, height=0.5, color=col, linewidth=0, label=sec if i == 0 else None,
                edgecolor=SURFACE)
        if v >= 2:
            ax.text(left + v / 2, i, str(v), ha="center", va="center", color=SURFACE if k in (0, 1) else TEXT,
                    fontsize=10)
        left += v + 0.15  # 2px surface gap between segments
    ax.text(left + 0.4, i, f"{sum(LOST[m])} lost", va="center", ha="left", color=TEXT, fontsize=12, weight="bold")
# full legend (all sections, including those at 0 for the first model)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in SECTION_COLOR]
ax.legend(handles, SECTIONS, loc="lower left", frameon=False, ncol=3, bbox_to_anchor=(0, 1.0),
          fontsize=10, labelcolor=TEXT)
ax.set_yticks(range(len(order)), order, color=TEXT)
ax.set_xlim(0, 40)
ax.set_xlabel("Points lost across the three tasks (out of 300)")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", length=0)
title(fig, "Where the points were lost",
      "Summed over the three tasks. Robustness beyond the tests and code quality separate the models.")
fig.savefig(OUT / "3_points_lost_by_section.png")
plt.close(fig)

print("ok:", *(p.name for p in sorted(OUT.glob("*.png"))))
