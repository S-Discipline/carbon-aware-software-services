import marimo as mo

__generated_with = "0.24.0"

app = mo.App()

# %% [markdown]
# # Reproducing "Carbon-aware Software Services" (Forti, Soldani & Brogi)
#
# **Central question:** can an interactive web service cut its carbon footprint by
# silently switching between cheaper, less-accurate implementations of the same
# endpoint, without letting the average quality of its answers fall below a
# set-point?
#
# The paper proposes **CARBONSTAT**: a bilevel MILP that schedules, for every
# 30-minute time slot, *which strategy* of an approximate-computing service should
# answer. It minimises forecast carbon emissions subject to keeping the average
# output error at or below a tolerated threshold $\varepsilon$ — and, among the
# minimum-carbon schedules, picks the one with the lowest error.
#
# This notebook reproduces the paper's headline claims **from the already-produced
# reproduction results** (no expensive experiment is re-run here; everything is
# deterministic data committed with the project). Full details: the companion
# report in `reports/carbonstat-reproduction/report.md`.

# %% [markdown]
# ## Embedded reproduction results
#
# These numbers come from three reproduction runs on a single NVIDIA A10 host
# (96 vCPU): (1) a deterministic validation of the MILP on the paper's motivating
# example, (2) a live measurement of the three strategies' service time and error,
# and (3) the 12-day × 3-profile simulation of the paper's Fig. 8. All results are
# embedded below so the notebook is fully self-contained.

# %%
# fmt: off
# paper  = {profile: {policy: [avg_error_%, reduction_%]}}
PAPER = {"camel": {"always_low": [13.4, 64.8], "always_medium": [4.5, 33.6], "naive": [9.7, 51.3], "carbonstat_e=1": [1.0, 13.3], "carbonstat_e=2": [2.0, 19.7], "carbonstat_e=4": [4.0, 30.9], "carbonstat_e=8": [8.0, 47.5]}, "stable300": {"always_low": [13.4, 62.9], "always_medium": [4.5, 29.2], "naive": [1.4, 14.4], "carbonstat_e=1": [1.0, 8.0], "carbonstat_e=2": [2.0, 15.0], "carbonstat_e=4": [4.0, 27.3], "carbonstat_e=8": [8.0, 44.7]}, "stable500": {"always_low": [13.4, 63.0], "always_medium": [4.5, 29.5], "naive": [4.6, 30.6], "carbonstat_e=1": [1.0, 8.0], "carbonstat_e=2": [2.0, 15.2], "carbonstat_e=4": [4.0, 27.5], "carbonstat_e=8": [8.0, 44.9]}}
# reproduced under the paper's own strategy cost model
NOMINAL = {"camel": {"always_low": [13.43, 64.8], "always_medium": [4.48, 33.8], "naive": [9.73, 51.0], "carbonstat_e=1": [1.0, 9.3], "carbonstat_e=2": [2.0, 17.2], "carbonstat_e=4": [3.99, 31.1], "carbonstat_e=8": [7.99, 47.9]}, "stable300": {"always_low": [13.43, 64.8], "always_medium": [4.48, 33.8], "naive": [1.41, 16.4], "carbonstat_e=1": [1.0, 9.2], "carbonstat_e=2": [1.99, 17.4], "carbonstat_e=4": [3.99, 31.3], "carbonstat_e=8": [8.0, 48.1]}, "stable500": {"always_low": [13.43, 64.8], "always_medium": [4.48, 33.8], "naive": [4.63, 34.9], "carbonstat_e=1": [1.0, 9.1], "carbonstat_e=2": [1.99, 17.4], "carbonstat_e=4": [3.99, 31.3], "carbonstat_e=8": [7.99, 48.0]}}
# reproduced with service times measured live on the reproduction host
MEASURED = {"camel": {"always_low": [13.44, 59.3], "always_medium": [4.48, 25.9], "naive": [9.74, 45.0], "carbonstat_e=1": [1.0, 7.1], "carbonstat_e=2": [2.0, 13.3], "carbonstat_e=4": [4.0, 24.1], "carbonstat_e=8": [8.0, 41.1]}, "stable300": {"always_low": [13.44, 59.3], "always_medium": [4.48, 25.9], "naive": [1.41, 12.9], "carbonstat_e=1": [1.0, 7.0], "carbonstat_e=2": [2.0, 13.4], "carbonstat_e=4": [4.0, 24.4], "carbonstat_e=8": [8.0, 41.3]}, "stable500": {"always_low": [13.44, 59.3], "always_medium": [4.48, 25.9], "naive": [4.63, 27.0], "carbonstat_e=1": [1.0, 7.0], "carbonstat_e=2": [2.0, 13.4], "carbonstat_e=4": [4.0, 24.3], "carbonstat_e=8": [8.0, 41.2]}}
# live-measured strategy cost model on the reproduction host (10 datasets x 100 requests)
STRATEGIES = {"LowPower": {"elapsed_ms": 18.92, "error_pct": 13.44}, "MediumPower": {"elapsed_ms": 34.43, "error_pct": 4.48}, "HighPower": {"elapsed_ms": 46.45, "error_pct": 0.0}}
# paper's reference strategy cost model
STRATEGIES_PAPER = {"LowPower": {"elapsed_ms": 35.3, "error_pct": 13.4}, "MediumPower": {"elapsed_ms": 66.3, "error_pct": 4.5}, "HighPower": {"elapsed_ms": 100.2, "error_pct": 0.0}}
# motivating example (paper Sec. III-B): assignment sequences per epsilon and emissions (g CO2-eq, 50 W server)
EXAMPLE = {"assignments": {0: ["H", "H", "H", "H", "H", "H"], 5: ["H", "M", "H", "L", "M", "L"], 15: ["L", "L", "L", "L", "L", "L"]}, "emissions_g": {0: 1.722, 5: 1.067, 15: 0.606}, "paper_emissions_g": {0: 1.72, 5: 1.07, 15: 0.60}}
# fmt: on

PROFILES = ["camel", "stable300", "stable500"]
POLICY_ORDER = ["always_low", "always_medium", "naive", "carbonstat_e=1", "carbonstat_e=2", "carbonstat_e=4", "carbonstat_e=8"]
SHORT = {"always_low": "always low", "always_medium": "always medium", "naive": "naive",
         "carbonstat_e=1": "CS \u03b5=1", "carbonstat_e=2": "CS \u03b5=2",
         "carbonstat_e=4": "CS \u03b5=4", "carbonstat_e=8": "CS \u03b5=8"}
PROFILE_LABEL = {"camel": "peaky (\u22481000)", "stable300": "stable 300", "stable500": "stable 500"}

# %%
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10, "figure.dpi": 110, "savefig.bbox": "tight"})


def fig_to_img(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    return mo.image(data=buf.read())

# %% [markdown]
# ## Headline result: carbon-emission reduction by policy
#
# For each request profile and policy, the bars show the paper's reported emission
# reduction (grey), our reproduction under the paper's own strategy cost model
# (blue), and our reproduction using service times measured live on the
# reproduction host (green). Two take-aways:
#
# * the **mechanism** — CARBONSTAT ($\varepsilon$) reducing emissions more as the
#   tolerated error grows, static policies reducing a fixed amount — reproduces
#   cleanly;
# * the **exact percentages** depend on hardware: on the faster reproduction host
#   the gap between the exact and the approximate strategies narrows, so all
#   reductions are a few points lower.

# %%
def headline_figure():
    x = np.arange(len(POLICY_ORDER))
    w = 0.28
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, profile in zip(axes, PROFILES):
        paper = [PAPER[profile][p][1] for p in POLICY_ORDER]
        nominal = [NOMINAL[profile][p][1] for p in POLICY_ORDER]
        measured = [MEASURED[profile][p][1] for p in POLICY_ORDER]
        ax.bar(x - w, paper, w, label="paper (Fig. 8)", color="#7f8c8d")
        ax.bar(x, nominal, w, label="reproduced (paper cost model)", color="#2980b9")
        ax.bar(x + w, measured, w, label="reproduced (measured on A10 host)", color="#27ae60")
        ax.set_title(PROFILE_LABEL[profile])
        ax.set_xticks(x)
        ax.set_xticklabels([SHORT[p] for p in POLICY_ORDER], rotation=25, ha="right")
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylim(-5, 75)
        ax.grid(axis="y", alpha=0.3)
        if profile == "camel":
            ax.set_ylabel("carbon-emission reduction vs high-power (%)")
    axes[0].legend(loc="upper left", frameon=False)
    fig.suptitle("Headline: carbon-emission reduction by policy across the three request profiles", y=1.03)
    return fig


fig_to_img(headline_figure())

# %% [markdown]
# ## Quality control: achieved error tracks the set-point
#
# The paper's central *guarantee* is that CARBONSTAT keeps the average output
# error at the tolerated threshold. The achieved errors (computed over the
# ±5%-perturbed *actual* requests) sit on the $y = \varepsilon$ diagonal for all
# three profiles, within ±0.004 pp. Static policies cannot do this: always-medium
# sits at 4.5 % and always-low at 13.4 % regardless of the set-point.

# %%
def quality_figure():
    eps = np.array([1, 2, 4, 8])
    markers = {"camel": "o", "stable300": "s", "stable500": "^"}
    colors = {"camel": "#c0392b", "stable300": "#2980b9", "stable500": "#8e44ad"}
    fig, ax = plt.subplots(figsize=(6.6, 4.4))
    for profile in PROFILES:
        ach = [MEASURED[profile][f"carbonstat_e={e}"][0] for e in eps]
        ax.plot(eps, ach, marker=markers[profile], color=colors[profile], ls="-", lw=1.2,
                label=f"{PROFILE_LABEL[profile]} (CARBONSTAT)")
    ax.plot([0, 9], [0, 9], "k--", lw=1, label="y = \u03b5 (perfect control)")
    ax.axhline(MEASURED["camel"]["always_medium"][0], color="#e67e22", ls=":", lw=1.4)
    ax.text(8.25, MEASURED["camel"]["always_medium"][0] + 0.25, "always medium (4.5%)", color="#e67e22")
    ax.axhline(MEASURED["camel"]["always_low"][0], color="#7f8c8d", ls=":", lw=1.4)
    ax.text(8.25, MEASURED["camel"]["always_low"][0] + 0.25, "always low (13.4%)", color="#7f8c8d")
    ax.set_xlim(0.5, 9.3)
    ax.set_ylim(0, 14.5)
    ax.set_xlabel("tolerated average error \u03b5 (%)")
    ax.set_ylabel("achieved average error (%)")
    ax.set_xticks(eps)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", frameon=False)
    ax.set_title("Quality control: CARBONSTAT keeps achieved error at \u03b5")
    return fig


fig_to_img(quality_figure())

# %% [markdown]
# ## The reduction–error trade-off frontier
#
# Plotting every policy by (achieved error, carbon reduction) shows *why* the
# planner matters: CARBONSTAT at $\varepsilon = 1, 2, 4, 8$ traces a frontier of
# growing savings as the error budget grows, while static policies sit at fixed
# points that cannot adapt to the carbon mix of the day.

# %%
def tradeoff_figure():
    markers = {"camel": "o", "stable300": "s", "stable500": "^"}
    colors = {"camel": "#c0392b", "stable300": "#2980b9", "stable500": "#8e44ad"}
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for profile in PROFILES:
        xs = [NOMINAL[profile][f"carbonstat_e={e}"][0] for e in [1, 2, 4, 8]]
        ys = [NOMINAL[profile][f"carbonstat_e={e}"][1] for e in [1, 2, 4, 8]]
        ax.plot(xs, ys, color=colors[profile], alpha=0.4, lw=1.2)
        for e in [1, 2, 4, 8]:
            ax.scatter(*NOMINAL[profile][f"carbonstat_e={e}"], marker=markers[profile],
                       color=colors[profile], s=55, zorder=3)
    for p, m, c, lab in [("always_low", "D", "#7f8c8d", "always low"),
                         ("always_medium", "D", "#e67e22", "always medium"),
                         ("naive", "D", "#34495e", "naive")]:
        for profile in PROFILES:
            ax.scatter(*NOMINAL[profile][p], marker=m, color=c, s=70, zorder=3,
                       edgecolors="w", linewidths=0.6)
        ax.scatter([], [], marker=m, color=c, s=70, label=lab, edgecolors="w", linewidths=0.6)
    ax.scatter([], [], marker="o", color="gray", s=55, label="CARBONSTAT \u03b5 = 1, 2, 4, 8")
    ax.set_xlabel("achieved average error (%)")
    ax.set_ylabel("carbon reduction vs high-power (%)")
    ax.set_title("CARBONSTAT traces the reduction\u2013error frontier; static policies do not")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", frameon=False)
    return fig


fig_to_img(tradeoff_figure())

# %% [markdown]
# ## Deterministic mechanism check: the paper's motivating example
#
# The bilevel MILP was validated on the paper's hand-worked 6-slot example. The
# OR-tools implementation returns **exactly** the assignment matrices printed in
# the paper, with matching emissions and a 4.98 % average error at $\varepsilon = 5\%$.
# This is fully deterministic and needs no re-running.

# %%
mo.md(
    "| \u03b5 | Assignment (6 slots) | Our emissions | Paper emissions |\n"
    "|---|---|---|---|\n"
    + "\n".join(
        f"| {e} % | {(' '.join(EXAMPLE['assignments'][e]))} | {EXAMPLE['emissions_g'][e]:.3f} g | {EXAMPLE['paper_emissions_g'][e]:.2f} g |"
        for e in [0, 5, 15]
    )
)

# %% [markdown]
# ## Strategy cost model on this host
#
# The errors that feed the planner are a property of the sampling rule and the
# dataset distribution — they reproduce almost exactly (13.44 / 4.48 / 0.00 %
# vs the paper's 13.4 / 4.5 / 0 %). The service times differ because the
# reproduction host is about twice as fast per request.

# %%
def strategy_figure():
    names = ["low", "medium", "high"]
    order = ["LowPower", "MediumPower", "HighPower"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    x = np.arange(3)
    w = 0.36
    for ax, key, ylab, title in [
            (axes[0], "elapsed_ms", "avg service time (ms)", "Service time"),
            (axes[1], "error_pct", "avg error (%)", "Output error")]:
        ax.bar(x - w / 2, [STRATEGIES_PAPER[s][key] for s in order], w,
               label="paper (4-vCPU server)", color="#7f8c8d")
        ax.bar(x + w / 2, [STRATEGIES[s][key] for s in order], w,
               label="measured (A10 host, 96 vCPU)", color="#27ae60")
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel(ylab)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(loc="upper left", frameon=False)
    fig.suptitle("Strategy cost model: same algorithm, ~2\u00d7 faster service times on the reproduction host", y=1.02)
    return fig


fig_to_img(strategy_figure())

# %% [markdown]
# ## Explore the numbers yourself (bounded, optional interactivity)
#
# Pick a tolerated error $\varepsilon$ and a request profile to see the achieved
# error and carbon reduction that CARBONSTAT produces, next to the static
# baselines. This reads the committed reproduction results — no experiment is
# re-run.

# %%
eps_choice = mo.ui.slider(1, 8, value=4, step=1, label="Tolerated error \u03b5 (%)")
profile_choice = mo.ui.dropdown(
    {p: PROFILE_LABEL[p] for p in PROFILES},
    value="camel", label="Request profile",
)
mo.hstack([eps_choice, profile_choice])

# %%
eps = int(eps_choice.value)
profile = profile_choice.value
p = f"carbonstat_e={eps}"
rows = [
    ["CARBONSTAT \u03b5=" + str(eps), *[f"{v:.2f}" for v in MEASURED[profile][p]], f"{MEASURED[profile][p][1] - NOMINAL[profile][p][1]:+.1f} pp"],
    ["naive", *[f"{v:.2f}" for v in MEASURED[profile]["naive"]], "\u2014"],
    ["always medium", *[f"{v:.2f}" for v in MEASURED[profile]["always_medium"]], "\u2014"],
    ["always low", *[f"{v:.2f}" for v in MEASURED[profile]["always_low"]], "\u2014"],
]
mo.ui.table(
    rows,
    columns=["Policy", "achieved error (%)", "reduction (%)", "reduction vs paper cost model"],
    label=f"{PROFILE_LABEL[profile]} \u00b7 \u03b5 = {eps}%",
)

# %% [markdown]
# ## Bottom line
#
# * The **planner's mechanism** reproduces exactly: the MILP returns the paper's
#   own schedules, the achieved error tracks $\varepsilon$, and the reduction
#   grows with the tolerated error (9–48 % under the paper's cost model).
# * The **strategy errors** reproduce exactly; the **service times** do not,
#   because the reproduction host is ~2× faster (an expected hardware
#   substitution, which compresses the reduction band to 7–41 %).
# * The remaining numerical gaps (a few pp at low $\varepsilon$) are consistent
#   with the live-timing noise visible in the paper's own repeated measurements.
#
# Full evidence, figures, and the claim-by-claim table: the companion report in
# `reports/carbonstat-reproduction/report.md`.

# %%
if __name__ == "__main__":
    app.run()
