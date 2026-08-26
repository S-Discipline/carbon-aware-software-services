#!/usr/bin/env python3
"""Runner for the CARBONSTAT reproduction (Forti, Soldani, Brogi 2025).

Modes are selected by config/experiment.json:
  - "motivating-example" : deterministic validation of the MILP vs paper Section III-B
  - "strategies-measure" : live measurement of strategy service time / error on this host
  - "main-sim"           : 12-day x 3-profile simulation of the paper's Fig. 8 policies

Every mode prints an evidence block: variant, effective config, final metrics,
and a compact summary.
"""
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CONFIG = os.path.join(ROOT, "config")


def load_experiment_config():
    with open(os.path.join(CONFIG, "experiment.json")) as f:
        cfg = json.load(f)
    return cfg


def log(*a):
    print(*a, flush=True)


# ----------------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------------
def run_carbonstat(input_time_slots, error_threshold, output_assignment):
    """Invoke the official carbonstat.py MILP as a subprocess (faithful)."""
    cmd = [
        sys.executable,
        os.path.join(ROOT, "carbonstat", "carbonstat.py"),
        input_time_slots,
        os.path.join(CONFIG, "strategies.csv"),
        str(error_threshold),
        output_assignment,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"carbonstat failed: {out.stderr}")
    return out.stdout


def parse_assignment(output_assignment):
    """Return {time_slot: strategy}. Keys collide if timestamps repeat."""
    strategy_of_slot = {}
    with open(output_assignment) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            slot, strategy = line.strip().split(",")[:2]
            strategy_of_slot[slot] = strategy
    return strategy_of_slot


def parse_assignment_ordered(output_assignment):
    """Return the list of strategies in file (slot) order."""
    seq = []
    with open(output_assignment) as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            seq.append(line.strip().split(",")[1])
    return seq


def read_strategy_stats(path):
    """Return {strategy: {elapsed_ms, error_pct}} and ordering."""
    stats = {}
    order = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i == 0:
                order.append(row["strategy"])
            stats[row["strategy"]] = {
                "elapsed_ms": float(row["elapsed_time"]),
                "error_pct": float(row["error"]),
            }
    # note: header row is data in the official files; keep all rows
    return stats, order


# emissions of one request (mg CO2): carbon g/kWh *1000 * 0.05 kW * hours
def emissions_mg(elapsed_ms, carbon_intensity):
    power_consumption = 0.05  # kWh (50 W server)
    hours = elapsed_ms / (3600.0 * 1000.0)
    mg_co2_kwh = carbon_intensity * 1000.0
    return mg_co2_kwh * power_consumption * hours


# ----------------------------------------------------------------------------
# MODE 1: motivating example (paper Section III-B)
# ----------------------------------------------------------------------------
def mode_motivating_example():
    log("=" * 78)
    log("MODE: motivating-example — paper Section III-B (deterministic MILP check)")
    log("=" * 78)
    example = os.path.join(DATA, "paper_example.csv")

    # r, c from the paper
    with open(example) as f:
        rows = list(csv.DictReader(f))
    requests = [int(r["forecast_reqs"]) for r in rows]
    carbon = [int(r["forecast_carbon"]) for r in rows]
    nominal = read_strategy_stats(os.path.join(CONFIG, "strategies.csv"))[0]

    paper_assignments = {0: ["HighPower"] * 6, 15: ["LowPower"] * 6,
                         5: ["HighPower", "MediumPower", "HighPower",
                             "LowPower", "MediumPower", "LowPower"]}

    summary = []
    for eps in [0, 5, 15]:
        out_csv = os.path.join(DATA, "tmp_assignment.csv")
        stdout = run_carbonstat(example, eps, out_csv)
        seq = parse_assignment_ordered(out_csv)

        # emissions with the paper's nominal service times (unrounded), 50W formula
        co2_mg = sum(
            requests[i] * carbon[i] * nominal[s]["elapsed_ms"]
            for i, s in enumerate(seq)
        ) * 0.05 * 1000.0 / (3600.0 * 1000.0)
        co2_g = co2_mg / 1000.0

        # average error (paper e values, weighted by requests)
        tot_req = sum(requests)
        avg_err = sum(requests[i] * nominal[s]["error_pct"] for i, s in enumerate(seq)) / tot_req

        log(f"\n--- epsilon = {eps}% ---")
        log(f"assignment          : {seq}")
        log(f"paper assignment    : {paper_assignments[eps]}")
        log(f"assignment matches  : {seq == paper_assignments[eps]}")
        log(f"emissions (50W)     : {co2_g:.4f} gCO2-eq")
        log(f"avg error           : {avg_err:.2f} %")
        log("carbonstat stdout   :")
        for line in stdout.strip().splitlines():
            log("  " + line.strip())
        summary.append({"eps": eps, "seq": seq, "co2_g": co2_g, "avg_err": avg_err})

    high = summary[0]["co2_g"]      # eps=0
    mixed = summary[1]["co2_g"]     # eps=5
    low = summary[2]["co2_g"]       # eps=15
    log("\n" + "=" * 78)
    log("SUMMARY (motivating example)")
    log("=" * 78)
    log(f"high-power  : {high:.3f} gCO2-eq   (paper: 1.72 gCO2-eq)")
    log(f"low-power   : {low:.3f} gCO2-eq   (paper: 0.60 gCO2-eq, -65.1% vs high)")
    log(f"eps=5 mixed : {mixed:.3f} gCO2-eq   (paper: 1.07 gCO2-eq, -37.8% vs high, +43.9% vs low)")
    log(f"reduction low vs high : {(1 - low / high) * 100:.1f}%   (paper: 65.1%)")
    log(f"reduction eps5 vs high: {(1 - mixed / high) * 100:.1f}%   (paper: 37.8%)")
    log(f"eps=5 avg error       : {summary[1]['avg_err']:.2f} %   (paper: 4.98 %)")
    ok = all(s["seq"] == paper_assignments[s["eps"]] for s in summary)
    log(f"all assignments match paper : {ok}")


# ----------------------------------------------------------------------------
# MODE 2: live strategy measurement
# ----------------------------------------------------------------------------
def generate_dataset():
    """Generate data/numbers.txt exactly as the Dockerfile did (SystemRandom)."""
    cwd = os.getcwd()
    try:
        os.chdir(DATA)
        subprocess.run([sys.executable, os.path.join(ROOT, "carbonstat", "generate_numbers.py")],
                       check=True)
    finally:
        os.chdir(cwd)
    numbers_path = os.path.join(DATA, "numbers.txt")
    assert os.path.exists(numbers_path), "dataset generation failed"
    return numbers_path


def service_ready(base_url, tries=120):
    import requests
    for _ in range(tries):
        try:
            r = requests.get(base_url + "/avg?force=HighPower", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def launch_service():
    """Run the Flask service as a plain process (docker-free substitution)."""
    env = dict(os.environ)
    env["ASSIGNMENT"] = os.path.join(DATA, "assignments", "example.csv")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "carbonstat", "carbon-aware-service.py")],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def mode_strategies_measure():
    import requests
    n_iterations = int(load_experiment_config().get("iterations", 10))
    n_requests = int(load_experiment_config().get("requests_per_strategy", 100))
    strategies = ["LowPower", "MediumPower", "HighPower"]
    log("=" * 78)
    log("MODE: strategies-measure — live service time/error on this host")
    log(f"iterations={n_iterations}  requests_per_strategy={n_requests}")
    log("=" * 78)

    base = "http://127.0.0.1:50000"
    raw = {s: [] for s in strategies}
    errors = {s: [] for s in strategies}
    times = {s: [] for s in strategies}

    for it in range(n_iterations):
        generate_dataset()          # fresh random dataset per iteration
        proc = launch_service()
        try:
            if not service_ready(base):
                raise RuntimeError("service did not become ready")
            correct = requests.get(base + "/avg?force=HighPower", timeout=10).json()["value"]
            for s in strategies:
                t0 = time.time()
                for _ in range(n_requests):
                    resp = requests.get(base + f"/avg?force={s}", timeout=10).json()
                    val = float(resp["value"])
                    elapsed = float(resp["elapsed"])
                    times[s].append(elapsed)
                    errors[s].append(abs(val - correct) / correct * 100.0)
                dt = time.time() - t0
                log(f"iter {it + 1}: {s:<12} mean elapsed {sum(times[s][-n_requests:])/n_requests:7.2f} ms"
                    f"   mean error {sum(errors[s][-n_requests:])/n_requests:6.3f} %   ({dt:.1f}s)")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    log("\n" + "=" * 78)
    log("SUMMARY (strategy characteristics on this host)")
    log("=" * 78)
    measured = {}
    for s in strategies:
        mt = sum(times[s]) / len(times[s])
        me = sum(errors[s]) / len(errors[s])
        measured[s] = {"elapsed_ms": mt, "error_pct": me}
        log(f"{s:<12} avg elapsed {mt:7.2f} ms   avg error {me:6.3f} %   "
            f"(paper: {35.3 if s == 'LowPower' else 66.3 if s == 'MediumPower' else 100.2} ms / "
            f"{13.4 if s == 'LowPower' else 4.5 if s == 'MediumPower' else 0.0} %)")

    # write measured stats for downstream nodes
    out_path = os.path.join(CONFIG, "strategies_measured.csv")
    with open(out_path, "w") as f:
        f.write("strategy,elapsed_time,error\n")
        for s in strategies:
            f.write(f"{s},{measured[s]['elapsed_ms']:.4f},{measured[s]['error_pct']:.4f}\n")
    log(f"measured stats written to {out_path}")


# ----------------------------------------------------------------------------
# MODE 3: main simulation (Fig. 8 reproduction)
# ----------------------------------------------------------------------------
def naive_strategy(forecast_carbon, forecast_reqs):
    """Replica of one_iteration.py run_naive (official thresholds)."""
    if forecast_carbon < 199 and forecast_reqs < 330:
        return "HighPower"
    if forecast_carbon < 299 and forecast_reqs < 660:
        return "MediumPower"
    return "LowPower"


def mode_main_sim():
    log("=" * 78)
    log("MODE: main-sim — Fig. 8 reproduction (12 days x 3 profiles)")
    log("=" * 78)

    cfg = load_experiment_config()
    traces_root = os.path.join(DATA, "traces")
    profiles = cfg.get("profiles", ["camel", "stable300", "stable500"])
    errors_eps = [1, 2, 4, 8]
    policies = (["always_low", "always_medium", "always_high", "naive"]
                + [f"carbonstat_e={e}" for e in errors_eps])

    # reference paper numbers (error %, reduction %) per profile
    paper = {
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

    # choose strategy stats
    stats_path = os.path.join(CONFIG, "strategies_measured.csv")
    stats_src = "measured"
    if not os.path.exists(stats_path):
        stats_path = os.path.join(CONFIG, "strategies.csv")
        stats_src = "nominal"
    nominal, _ = read_strategy_stats(os.path.join(CONFIG, "strategies.csv"))
    measured, _ = read_strategy_stats(stats_path)
    stats = measured if stats_src == "measured" else nominal
    log(f"strategy stats source: {stats_src}")
    for s in ["LowPower", "MediumPower", "HighPower"]:
        log(f"  {s:<12} elapsed {stats[s]['elapsed_ms']:.2f} ms  error {stats[s]['error_pct']:.3f} %")

    results = {}
    for profile in profiles:
        pdir = os.path.join(traces_root, profile)
        days = sorted(os.listdir(os.path.join(pdir, "values")))
        log(f"\nprofile {profile}: {len(days)} days")

        assignments = {}
        for e in errors_eps:
            assignments[e] = {}
            for d in days:
                apath = os.path.join(pdir, f"error_{e:02d}", f"assignment_{d}")
                assignments[e][d] = parse_assignment(apath)

        agg = {p: {"carbon_mg": 0.0, "err_w": 0.0, "reqs": 0, "max_err": 0.0} for p in policies}
        for d in days:
            with open(os.path.join(pdir, "values", d)) as f:
                rows = list(csv.DictReader(f))
            for row in rows:
                slot = row["time"]
                c_actual = int(row["actual_carbon"])
                c_forecast = int(row["forecast_carbon"])
                r_actual = int(row["actual_reqs"])
                r_forecast = int(float(row["forecast_reqs"]))
                if r_actual == 0:
                    continue
                slot_policies = {
                    "always_low": "LowPower",
                    "always_medium": "MediumPower",
                    "always_high": "HighPower",
                    "naive": naive_strategy(c_forecast, r_forecast),
                }
                for e in errors_eps:
                    slot_policies[f"carbonstat_e={e}"] = assignments[e][d][slot]
                for p in policies:
                    s = slot_policies[p]
                    e_pct = stats[s]["error_pct"]
                    t_ms = stats[s]["elapsed_ms"]
                    agg[p]["carbon_mg"] += emissions_mg(t_ms, c_actual) * r_actual
                    agg[p]["err_w"] += e_pct * r_actual
                    agg[p]["reqs"] += r_actual
                    agg[p]["max_err"] = max(agg[p]["max_err"], e_pct)

        results[profile] = {}
        high_carbon = agg["always_high"]["carbon_mg"]
        for p in policies:
            avg_err = agg[p]["err_w"] / agg[p]["reqs"]
            reduction = (1 - agg[p]["carbon_mg"] / high_carbon) * 100.0
            results[profile][p] = {"err": avg_err, "red": reduction,
                                   "carbon_mg": agg[p]["carbon_mg"]}
            ref = paper[profile].get(p)
            ref_str = f"paper err/red {ref[0]}/{ref[1]}" if ref else ""
            log(f"  {p:<18} err {avg_err:5.2f} %   red {reduction:5.1f} %   "
                f"carbon {agg[p]['carbon_mg']/1000:.2f} g   {ref_str}")

    log("\n" + "=" * 78)
    log("SUMMARY (quality guarantee check): achieved avg error vs threshold")
    log("=" * 78)
    for profile in profiles:
        line = []
        for e in errors_eps:
            err = results[profile][f"carbonstat_e={e}"]["err"]
            line.append(f"eps={e}: {err:.2f}% {'OK' if err <= e + 1e-9 else 'EXCEEDED'}")
        log(f"{profile:<12} " + "  ".join(line))

    log("\nDONE main-sim")


# ----------------------------------------------------------------------------
# entry point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    mode = load_experiment_config().get("mode", "motivating-example")
    log(f"experiment.json mode = {mode}")
    if mode == "motivating-example":
        mode_motivating_example()
    elif mode == "strategies-measure":
        mode_strategies_measure()
    elif mode == "main-sim":
        mode_main_sim()
    else:
        sys.exit(f"unknown mode: {mode}")
