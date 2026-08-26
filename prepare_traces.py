#!/usr/bin/env python3
"""Generate the experiment traces: real UK carbon intensity (Carbon Intensity
API) for 12 days of 2023 + lifelike request profiles.

Faithful port of the official data/experiment/trace_generator.py with three
documented changes:
  1. random.seed(42) for reproducibility (official had it commented out);
  2. support for a stable-500 request profile (paper Fig. 7(c); official code
     only implemented the stable-300 profile);
  3. None carbon intensity values fall back to the forecast (API gap guard).

Outputs under data/traces/<profile>/:
  values/m<NN>.csv                      per-slot actual/forecast carbon + requests
  error_<EE>/assignment_m<NN>.csv       carbonstat MILP assignments per threshold
"""
import csv
import os
import random
import subprocess
import sys
import time
from datetime import timedelta

import requests
from dateutil import parser as date_parser

ROOT = os.path.dirname(os.path.abspath(__file__))
TRACES = os.path.join(ROOT, "data", "traces")

PROFILES = {
    "camel":      [(4, 100), (8, 500), (12, 1000), (16, 500), (20, 1000), (24, 300)],
    "stable300":  [(4, 300), (8, 300), (12, 300), (16, 300), (20, 300), (24, 300)],
    "stable500":  [(4, 500), (8, 500), (12, 500), (16, 500), (20, 500), (24, 500)],
}


def download_emissions(date, retries=6):
    fr = date_parser.parse(date)
    to = fr + timedelta(days=1)
    url = "https://api.carbonintensity.org.uk/intensity/" + fr.isoformat() + "/" + to.isoformat()
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=60)
            r.raise_for_status()
            return r.json()["data"]
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt == retries - 1:
                raise
            print(f"    retrying download for {date} ({exc})", flush=True)
            time.sleep(5 * (attempt + 1))


def generate_reqs_trace(peaks):
    slots = []
    for k in range(len(peaks)):
        (h1, r1) = peaks[k]
        (h2, r2) = peaks[(k + 1) % len(peaks)]
        diff = r2 - r1
        steps = 2 * (h2 - h1) % 24
        inc = diff // steps
        for i in range(steps):
            step = r1 + inc * i
            res = step * (1 + random.uniform(-0.1, 0.1))
            slots.append(round(res))
    return slots


def main(profile, start_date="2023-01-28T00:30Z", days=12, step=28):
    assert profile in PROFILES, f"unknown profile {profile}"
    pdir = os.path.join(TRACES, profile)
    os.makedirs(os.path.join(pdir, "values"), exist_ok=True)
    for e in [1, 2, 4, 8]:
        os.makedirs(os.path.join(pdir, f"error_{e:02d}"), exist_ok=True)

    for d in range(days):
        date = date_parser.parse(start_date) + timedelta(days=d * step, hours=0, minutes=0)
        emissions = download_emissions(date.isoformat())
        reqs = generate_reqs_trace(PROFILES[profile])
        name = f"m{d + 1:02d}.csv"
        path = os.path.join(pdir, "values", name)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "actual_carbon", "forecast_carbon", "actual_reqs", "forecast_reqs"])
            for i in range(0, 48):
                intensity = emissions[i]["intensity"]
                actual = intensity["actual"]
                if actual is None:
                    actual = intensity["forecast"]
                writer.writerow([
                    emissions[i]["from"],
                    actual,
                    intensity["forecast"],
                    int(reqs[i] + reqs[i] * random.uniform(-0.05, 0.05)),
                    reqs[i],
                ])
        print(f"  {profile} day {d + 1}: {name} ({date.date()})")

        for e in [1, 2, 4, 8]:
            out = os.path.join(pdir, f"error_{e:02d}", f"assignment_{name}")
            subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "carbonstat", "carbonstat.py"),
                 path,
                 os.path.join(ROOT, "config", "strategies.csv"),
                 str(e),
                 out],
                check=True, capture_output=True)
    print(f"done: {pdir}")


if __name__ == "__main__":
    random.seed(42)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", nargs="?", default=None, help="camel | stable300 | stable500 (all if omitted)")
    args = ap.parse_args()
    targets = [args.profile] if args.profile else list(PROFILES)
    for p in targets:
        main(p)
