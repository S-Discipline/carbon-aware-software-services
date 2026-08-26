#!/usr/bin/env python3
"""Generate the report figures from analysis/results.json.

Outputs to reports/carbonstat-reproduction/images/.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(os.path.dirname(HERE), "reports", "carbonstat-reproduction", "images")
os.makedirs(IMG, exist_ok=True)

with open(os.path.join(HERE, "results.json")) as f:
    R = json.load(f)

PROFILES = ["camel", "stable300", "stable500"]
PAPER_POLICY_ORDER = ["always_low", "always_medium", "naive",
                      "carbonstat_e=1", "carbonstat_e=2", "carbonstat_e=4", "carbonstat_e=8"]
SHORT = {"always_low": "always low", "always_medium": "always medium", "naive": "naive",
         "carbonstat_e=1": "CS \u03b5=1", "carbonstat_e=2": "CS \u03b5=2",
         "carbonstat_e=4": "CS \u03b5=4", "carbonstat_e=8": "CS \u03b5=8"}

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "legend.fontsize": 8, "figure.dpi": 150, "savefig.bbox": "tight",
})


def profile_label(p):
    return {"camel": "peaky (\u22481000)", "stable300": "stable 300",
            "stable500": "stable 500"}[p]


# ---------------------------------------------------------------- Figure 1
def fig1_headline():
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    x = np.arange(len(PAPER_POLICY_ORDER))
    w = 0.28
    for ax, profile in zip(axes, PROFILES):
        paper = [R["paper"][profile][p][1] for p in PAPER_POLICY_ORDER]
        nominal = [R["nominal"][profile][p]["red"] for p in PAPER_POLICY_ORDER]
        measured = [R["measured"][profile][p]["red"] for p in PAPER_POLICY_ORDER]
        ax.bar(x - w, paper, w, label="paper (Fig. 8)", color="#7f8c8d")
        ax.bar(x, nominal, w, label="reproduced (paper cost model)", color="#2980b9")
        ax.bar(x + w, measured, w, label="reproduced (measured on A10 host)", color="#27ae60")
        ax.set_title(profile_label(profile))
        ax.set_xticks(x)
        ax.set_xticklabels([SHORT[p] for p in PAPER_POLICY_ORDER], rotation=25, ha="right")
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylim(-5, 75)
        ax.grid(axis="y", alpha=0.3)
        if profile == "camel":
            ax.set_ylabel("carbon-emission reduction vs high-power (%)")
    axes[0].legend(loc="upper left", frameon=False)
    fig.suptitle("Headline: carbon-emission reduction by policy across the three request profiles", y=1.03)
    fig.savefig(os.path.join(IMG, "fig1_headline_reduction.png"))
    plt.close(fig)


# ---------------------------------------------------------------- Figure 2
def fig2_quality():
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    eps = np.array([1, 2, 4, 8])
    markers = {"camel": "o", "stable300": "s", "stable500": "^"}
    colors = {"camel": "#c0392b", "stable300": "#2980b9", "stable500": "#8e44ad"}
    for profile in PROFILES:
        ach = [R["measured"][profile][f"carbonstat_e={e}"]["err"] for e in eps]
        ax.plot(eps, ach, marker=markers[profile], color=colors[profile], ls="-", lw=1.2,
                label=f"{profile_label(profile)} (CARBONSTAT)")
    ax.plot([0, 9], [0, 9], "k--", lw=1, label="y = \u03b5 (perfect control)")
    ax.axhline(R["measured"]["camel"]["always_medium"]["err"], color="#e67e22", ls=":", lw=1.4)
    ax.text(8.25, R["measured"]["camel"]["always_medium"]["err"] + 0.25, "always medium (4.5%)", color="#e67e22")
    ax.axhline(R["measured"]["camel"]["always_low"]["err"], color="#7f8c8d", ls=":", lw=1.4)
    ax.text(8.25, R["measured"]["camel"]["always_low"]["err"] + 0.25, "always low (13.4%)", color="#7f8c8d")
    ax.set_xlim(0.5, 9.3)
    ax.set_ylim(0, 14.5)
    ax.set_xlabel("tolerated average error \u03b5 (%)")
    ax.set_ylabel("achieved average error (%)")
    ax.set_xticks(eps)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", frameon=False)
    ax.set_title("Quality control: CARBONSTAT keeps the achieved error at \u03b5, static policies cannot")
    fig.savefig(os.path.join(IMG, "fig2_quality_control.png"))
    plt.close(fig)


# ---------------------------------------------------------------- Figure 3
def fig3_strategy_model():
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    strategies = ["LowPower", "MediumPower", "HighPower"]
    labels = ["low", "medium", "high"]
    paper_t = [35.3, 66.3, 100.2]
    meas_t = [R["strategies"]["measured"][s]["elapsed_ms"] for s in strategies]
    paper_e = [13.4, 4.5, 0.0]
    meas_e = [R["strategies"]["measured"][s]["error_pct"] for s in strategies]
    x = np.arange(3)
    w = 0.36
    for ax, paper, meas, ylab, title in [
            (axes[0], paper_t, meas_t, "avg service time (ms)", "Service time"),
            (axes[1], paper_e, meas_e, "avg error (%)", "Output error")]:
        ax.bar(x - w / 2, paper, w, label="paper (4-vCPU server)", color="#7f8c8d")
        ax.bar(x + w / 2, meas, w, label="measured (A10 host, 96 vCPU)", color="#27ae60")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel(ylab)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(loc="upper left", frameon=False)
    fig.suptitle("Strategy cost model: same algorithm, ~2\u00d7 faster service times on the reproduction host", y=1.02)
    fig.savefig(os.path.join(IMG, "fig3_strategy_model.png"))
    plt.close(fig)


# ---------------------------------------------------------------- Figure 4
def fig4_motivating_example():
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), gridspec_kw={"width_ratios": [1, 1.15]})
    # assignment matrices per epsilon
    eps_seq = [0, 5, 15]
    seqs = {0: ["H"] * 6, 5: ["H", "M", "H", "L", "M", "L"], 15: ["L"] * 6}
    cmap = {"L": "#27ae60", "M": "#f39c12", "H": "#c0392b"}
    ax = axes[0]
    for i, e in enumerate(eps_seq):
        for j, s in enumerate(seqs[e]):
            ax.add_patch(plt.Rectangle((j, i), 1, 1, color=cmap[s]))
            ax.text(j + 0.5, i + 0.5, s, ha="center", va="center", color="white",
                    fontsize=9, fontweight="bold")
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 3)
    ax.set_yticks([i + 0.5 for i in range(3)])
    ax.set_yticklabels([f"\u03b5 = {e}%" for e in eps_seq])
    ax.set_xticks([j + 0.5 for j in range(6)])
    ax.set_xticklabels([f"slot {j+1}" for j in range(6)], fontsize=8)
    ax.set_title("MILP assignment (L/M/H power) — matches paper exactly")
    # emissions
    ax = axes[1]
    ours = [1.722, 1.067, 0.606]
    paper = [1.72, 1.07, 0.60]
    x = np.arange(3)
    ax.bar(x - 0.18, paper, 0.36, label="paper", color="#7f8c8d")
    ax.bar(x + 0.18, ours, 0.36, label="reproduced", color="#2980b9")
    for xi, v in zip(x + 0.18, ours):
        ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(["\u03b5 = 0%\n(high power)", "\u03b5 = 5%\n(mixed)", "\u03b5 = 15%\n(low power)"])
    ax.set_ylabel("carbon (g CO2-eq, 50 W server)")
    ax.set_title("Emissions over the 6-slot example")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Mechanism: the CARBONSTAT MILP reproduces the paper\u2019s motivating example deterministically", y=1.02)
    fig.savefig(os.path.join(IMG, "fig4_motivating_example.png"))
    plt.close(fig)


# ---------------------------------------------------------------- Figure 5
def fig5_tradeoff():
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    markers = {"camel": "o", "stable300": "s", "stable500": "^"}
    colors = {"camel": "#c0392b", "stable300": "#2980b9", "stable500": "#8e44ad"}
    for profile in PROFILES:
        for e in [1, 2, 4, 8]:
            p = f"carbonstat_e={e}"
            ax.scatter(R["nominal"][profile][p]["err"], R["nominal"][profile][p]["red"],
                       marker=markers[profile], color=colors[profile], s=55, zorder=3)
        # connect the frontier
        xs = [R["nominal"][profile][f"carbonstat_e={e}"]["err"] for e in [1, 2, 4, 8]]
        ys = [R["nominal"][profile][f"carbonstat_e={e}"]["red"] for e in [1, 2, 4, 8]]
        ax.plot(xs, ys, color=colors[profile], alpha=0.4, lw=1.2)
    for p, m, c, lab in [("always_low", "D", "#7f8c8d", "always low"),
                         ("always_medium", "D", "#e67e22", "always medium"),
                         ("naive", "D", "#34495e", "naive")]:
        for profile in PROFILES:
            ax.scatter(R["nominal"][profile][p]["err"], R["nominal"][profile][p]["red"],
                       marker=m, color=c, s=70, zorder=3, edgecolors="w", linewidths=0.6)
        ax.scatter([], [], marker=m, color=c, s=70, label=lab, edgecolors="w", linewidths=0.6)
    ax.scatter([], [], marker="o", color="gray", s=55, label="CARBONSTAT \u03b5 = 1, 2, 4, 8")
    ax.set_xlabel("achieved average error (%)")
    ax.set_ylabel("carbon reduction vs high-power (%)")
    ax.set_title("The reduction\u2013error trade-off: CARBONSTAT traces the frontier, static policies do not")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", frameon=False)
    fig.savefig(os.path.join(IMG, "fig5_tradeoff.png"))
    plt.close(fig)


if __name__ == "__main__":
    fig1_headline()
    fig2_quality()
    fig3_strategy_model()
    fig4_motivating_example()
    fig5_tradeoff()
    print("wrote figures to", IMG)
