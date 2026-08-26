# Carbon-aware Software Services — reproduction of Forti, Soldani & Brogi (ESOCC 2025)

This repository reproduces the paper **"Carbon-aware Software Services"**
([arXiv:2405.12582](https://www.alphaxiv.org/abs/2405.12582)), which proposes
**CARBONSTAT**: a bilevel MILP that schedules, per 30-minute time slot, which
approximate-computing strategy an interactive service should run, minimising
forecast carbon emissions while keeping the average output error at or below a
tolerated threshold ε.

## What was tested and the result

**Tested claim (headline).** CARBONSTAT keeps the average output error at the
tolerated set-point ε while reducing carbon emissions by **8 %–50 %** relative
to a service that always runs the exact implementation.

**What was done.** Three experiments on the agreed compute (single NVIDIA A10
host, 96 vCPU / 251 GB RAM, SSH alias `ensembleci-a10`):

1. **Deterministic MILP check** on the paper's 6-slot motivating example.
2. **Live strategy measurement** — service times and errors of the three
   strategies measured on the reproduction host.
3. **Fig. 8 simulation** — 12 real UK days of 2023 × 3 request profiles × 8
   policies, with the official traces (the camel/peaky trace matches the
   paper's committed data row-for-row) and the officially shipped OR-tools
   optimizer.

**Assessment: the mechanism and quality claims reproduce exactly; the
reduction band reproduces in structure and approximately in value.**

| Quantity | Paper | Observed |
|---|---|---|
| Motivating-example schedules (ε = 0/5/15 %) | matrices in Sec. III-B | identical; emissions 1.72 / 1.07 / 0.61 g CO2-eq (paper 1.72 / 1.07 / 0.60) |
| Achieved average error at ε = 1/2/4/8 % | 1.0 / 2.0 / 4.0 / 8.0 % | 1.000 / 2.000 / 4.000 / 8.00 % (within ±0.004 pp), all profiles |
| Strategy errors (low/med/high) | 13.4 / 4.5 / 0 % | 13.44 / 4.48 / 0.00 % |
| Strategy service times | 35.3 / 66.3 / 100.2 ms | 18.9 / 34.4 / 46.5 ms (≈2× faster host) |
| Emission reduction band | 8 %–50 % | 9–48 % under the paper's cost model; 7–41 % with the host's measured times |
| CARBONSTAT ε=4, ε=8 reduction (peaky) | 30.9 / 47.5 % | 31.1 / 47.9 % |

**Downscaling / substitutions (documented):** traces regenerated with
`random.seed(42)` (the camel trace matches the paper's committed data exactly,
so this is faithful); the service runs as a plain process instead of Docker;
per-request wall-clock times are replaced by the live-measured per-strategy
means (expectation-equivalent, since per-request errors are deterministic on a
fixed dataset and carbon is linear in time). The paper's stable-profile traces
are not published, so those two profiles use regenerated traces and differ from
the paper by 1–4 pp on CARBONSTAT's reductions.

**Detailed evidence:**

- [Reproduction report](reports/carbonstat-reproduction/report.md) — full
  claim-by-claim analysis with five figures.
- [Interactive notebook](notebooks/carbonstat_reproduction.py) — self-contained
  marimo notebook that opens with the already-produced evidence (no experiment
  re-run needed). Run locally with `marimo edit notebooks/carbonstat_reproduction.py`
  or `marimo run notebooks/carbonstat_reproduction.py`.

## Experiment log

All experiment nodes run the same fixed command (set once on the root and
inherited), launched on the SSH compute with
`orx exp run <expId> --backend ssh --host ensembleci-a10`:

| Experiment / branch | Purpose / change | Exact run command | Assessment | Compute |
|---|---|---|---|---|
| `orx/milp-mechanism-motivating-example-sec-iii-b` (root) | Deterministic validation of the CARBONSTAT MILP on the paper's 6-slot example | `python3 reproduce.py` | **Aligned (exact)** — schedules, emissions (1.72/1.07/0.61 g), 4.98 % error all match | A10 host, 13 s |
| `orx/strategy-characteristics-on-compute` | Live-measure the three strategies on the reproduction host (10×100 requests, fresh datasets) | `python3 reproduce.py` | **Aligned on errors** (13.44/4.48/0 %); **times differ** (18.9/34.4/46.5 vs 35.3/66.3/100.2 ms) — hardware | A10 host, 2 m 40 s |
| `orx/fig-8-reproduction-12-days-x-3-profiles` | Fig. 8 simulation: 12 days × 3 profiles × 8 policies using measured cost model | `python3 reproduce.py` | **Quality aligned** (achieved error ≈ ε); **reduction aligned in structure**, 9–48 % (paper cost model) / 7–41 % (measured) | A10 host, 7 s |
| `main` | Publication surface: this README, report, figures, notebook, analysis | Not run as an experiment (publication surface) | — | — |

The per-node mode is selected by `config/experiment.json`; all results are
regenerated deterministically by `python3 analysis/summarize.py` from the
committed traces (`data/traces/`) and configurations.

## Reproducing from scratch

```bash
pip install -r requirements.txt            # ortools, flask, requests, python-dateutil
python3 prepare_traces.py                  # regenerate the 12-day traces + MILP assignments (needs network)
python3 reproduce.py                       # runs the mode in config/experiment.json
python3 analysis/summarize.py              # recompute the reported tables
```

`config/experiment.json` selects the mode: `motivating-example`,
`strategies-measure`, or `main-sim`.
