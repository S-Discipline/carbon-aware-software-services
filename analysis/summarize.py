#!/usr/bin/env python3
"""Recompute the reproduction results from committed traces/config (self-contained)
and emit analysis/results.csv + analysis/results.json for the report and notebook.

Purely deterministic — does not require ortools or flask.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from reproduce import (CONFIG, DATA, read_strategy_stats, parse_assignment,
                       naive_strategy, emissions_mg)

PAPER = {
    "camel":      {"always_low": (13.4, 64.8), "always_medium": (4.5, 33.6), "naive": (9.7, 51.3),
                   "carbonstat_e=1": (1.0, 13.3), "carbonstat_e=2": (2.0, 19.7),
                   "carbonstat_e=4": (4.0, 30.9), "carbonstat_e=8": (8.0, 47.5)},
    "stable300":  {"always_low": (13.4, 62.9), "always_medium": (4.5, 29.2), "naive": (1.4, 14.4),
                   "carbonstat_e=1": (1.0, 8.0), "carbonstat_e=2": (2.0, 15.0),
                   "carbonstat_e=4": (4.0, 27.3), "carbonstat_e=8": (8.0, 44.7)},
    "stable500":  {"always_low": (13.4, 63.0), "always_medium": (4.5, 29.5), "naive": (4.6, 30.6),
                   "carbonstat_e=1": (1.0, 8.0), "carbonstat_e=2": (2.0, 15.2),
                   "carbonstat_e=4": (4.0, 27.5), "carbonstat_e=8": (8.0, 44.9)},
}
ERROR_EPS = [1, 2, 4, 8]
POLICIES = (["always_low", "always_medium", "always_high", "naive"]
            + [f"carbonstat_e={e}" for e in ERROR_EPS])
PROFILES = ["camel", "stable300", "stable500"]


def compute_results(stats):
    """Return {profile: {policy: {err, red, carbon_mg}}} identical to main-sim."""
    traces_root = os.path.join(DATA, "traces")
    out = {}
    for profile in PROFILES:
        pdir = os.path.join(traces_root, profile)
        days = sorted(os.listdir(os.path.join(pdir, "values")))
        assignments = {}
        for e in ERROR_EPS:
            assignments[e] = {}
            for d in days:
                assignments[e][d] = parse_assignment(
                    os.path.join(pdir, f"error_{e:02d}", f"assignment_{d}"))
        agg = {p: {"carbon_mg": 0.0, "err_w": 0.0, "reqs": 0} for p in POLICIES}
        for d in days:
            with open(os.path.join(pdir, "values", d)) as f:
                rows = list(csv.DictReader(f))
            for row in rows:
                slot = row["time"]
                c_act, c_for = int(row["actual_carbon"]), int(row["forecast_carbon"])
                r_act, r_for = int(row["actual_reqs"]), int(float(row["forecast_reqs"]))
                if r_act == 0:
                    continue
                sp = {"always_low": "LowPower", "always_medium": "MediumPower",
                      "always_high": "HighPower",
                      "naive": naive_strategy(c_for, r_for)}
                for e in ERROR_EPS:
                    sp[f"carbonstat_e={e}"] = assignments[e][d][slot]
                for p in POLICIES:
                    s = sp[p]
                    agg[p]["carbon_mg"] += emissions_mg(stats[s]["elapsed_ms"], c_act) * r_act
                    agg[p]["err_w"] += stats[s]["error_pct"] * r_act
                    agg[p]["reqs"] += r_act
        out[profile] = {}
        high = agg["always_high"]["carbon_mg"]
        for p in POLICIES:
            out[profile][p] = {
                "err": agg[p]["err_w"] / agg[p]["reqs"],
                "red": (1 - agg[p]["carbon_mg"] / high) * 100.0,
                "carbon_mg": agg[p]["carbon_mg"],
            }
    return out


def main():
    nominal, _ = read_strategy_stats(os.path.join(CONFIG, "strategies.csv"))
    measured, _ = read_strategy_stats(os.path.join(CONFIG, "strategies_measured.csv"))

    res = {"measured": compute_results(measured), "nominal": compute_results(nominal),
           "strategies": {"measured": measured, "nominal": nominal}, "paper": PAPER}

    rows = []
    for profile in PROFILES:
        for p in POLICIES:
            pe, pr = PAPER[profile].get(p, (float("nan"), float("nan")))
            row = {"profile": profile, "policy": p,
                   "paper_err": pe, "paper_red": pr,
                   "nom_err": res["nominal"][profile][p]["err"],
                   "nom_red": res["nominal"][profile][p]["red"],
                   "meas_err": res["measured"][profile][p]["err"],
                   "meas_red": res["measured"][profile][p]["red"],
                   "meas_carbon_mg": res["measured"][profile][p]["carbon_mg"]}
            rows.append(row)

    with open(os.path.join(os.path.dirname(__file__), "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(os.path.dirname(__file__), "results.json"), "w") as f:
        json.dump(res, f, indent=2)

    print("wrote analysis/results.csv and analysis/results.json")
    print("\nquality-guarantee (achieved vs threshold, measured cost model):")
    for profile in PROFILES:
        line = []
        for e in ERROR_EPS:
            aerr = res["measured"][profile][f"carbonstat_e={e}"]["err"]
            line.append(f"eps={e}: {aerr:.4f}%")
        print(f"  {profile:<12} " + "  ".join(line))


if __name__ == "__main__":
    main()
