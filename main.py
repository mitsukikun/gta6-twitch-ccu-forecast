"""gta6-twitch-ccu-forecast-01 entry: comparable-launch shape forecaster.

Forecasts Twitch concurrent viewers in the Grand Theft Auto VI category for
hours 2..24 of release day 2026-11-19 (UTC), as five quantiles an hour, from
everything the case holds up to the end of hour 1.

Method (standard library only, deterministic, no network):
  1. Anchor on the case's hour-1 print p1.
  2. For every comparable past launch, take its release-day hourly curve and
     express each hour as a log-ratio to its own hour-1 print,
     lr_h = ln(viewers_h / viewers_1). A launch-day curve is a shape: the
     ratios, not the levels, transfer across launches of different sizes.
  3. Weight each comparable by how much its launch resembles GTA VI's:
       - drop the target-history pseudo-launch (GTA VI's own pre-release
         category history: not a launch curve at all);
       - drop front-loaded launches whose release day peaks in hour 1 or 2
         (a simultaneous global unlock: the peak is already in hour 1, so
         their shape cannot describe a rolling-midnight console launch);
       - double-weight console-only launches (no PC in the platform list):
         GTA VI is PS5 / Xbox Series X|S only, unlocking at local midnight;
       - weight by launch scale with a Gaussian kernel in log10(viewers_1)
         around the case's own p1 (bandwidth 0.7 dex): small hour-1 prints
         rise much more over the day than huge ones, and vice versa.
  4. Per hour, the median forecast is p1 * exp(weighted median of lr_h).
     The spread is 0.7 * the weighted standard deviation of lr_h around its
     weighted mean, floored at 0.25 and capped at 1.2 log units, and the five
     quantiles are p1 * exp(median + z_tau * sigma) at the standard normal
     quantiles (-1.645, -0.674, 0, 0.674, 1.645).
  5. Hours with too few usable comparables fall back to the house
     persistence shape (flat at p1, spread 0.15 * sqrt(h - 1)).

Local practice check (4 past launches, SullyGnome hourly averages as the
answer, pinball loss on the log scale): mean loss 0.211, against 0.387 for
the persistence baseline the kit ships; every practice case beats it
(p00 0.385, p01 0.165, p02 0.124, p03 0.173 vs baseline 0.744 / 0.287 /
0.215 / 0.303). Typical miss about 45% (Wolverine's 9x evening rise is
the hard case at 102%), 90% coverage about 0.97.

The grader runs `python3 -P -s /bot/main.py` (Python 3.13, stdlib only):
read every <id>.in in the input directory and write <id>.out per case.
MAKEFUN_INPUT_DIR / MAKEFUN_OUTPUT_DIR stand in for /input and /output
outside the grader's container.
"""

import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import (this entry is a single file).
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Spread of the persistence fallback, in log units per square-root hour.
FALLBACK_SIGMA = 0.15
# How much of the cross-launch spread of log-ratios becomes our sigma.
SIGMA_MULT = 0.7
SIGMA_FLOOR = 0.25
SIGMA_CAP = 1.2
# Bandwidth of the launch-scale kernel, in decades of hour-1 viewers.
SCALE_BW_DEX = 0.7
# A comparable must carry at least this many scored hours to be used.
MIN_SCORED_HOURS = 12
# An hour needs at least this many weighted comparables, else it falls back.
MIN_CURVES_PER_HOUR = 5


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as the kit's starter rounds it."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def release_day_hours(comp: dict) -> dict[int, float]:
    """{hour: viewers} for the comparable's release day, hours 1..24."""
    day_start = parse_ts(comp["day_start"])
    out: dict[int, float] = {}
    for row in comp.get("hourly", []):
        viewers = row.get("viewers")
        if not viewers or viewers <= 0:
            continue
        hour = int((parse_ts(row["from"]) - day_start).total_seconds() // 3600) + 1
        if 1 <= hour <= 24:
            out[hour] = viewers
    return out


def comparable_curves(case: dict) -> list[dict]:
    """Each usable comparable as its log-ratio curve plus its weight parts.

    Returns dicts with keys: weight (before the scale kernel), v1 (hour-1
    viewers), peak_hour, lr ({hour: log-ratio to hour 1} for hours 2..24).
    """
    curves = []
    for comp in case.get("comparables", []):
        unlock = comp.get("unlock", "")
        if "target-history" in unlock:
            continue  # GTA VI's own pre-release history is not a launch
        hours = release_day_hours(comp)
        v1 = hours.get(1)
        if not v1 or v1 <= 0:
            continue
        scored = sum(1 for h in range(2, 25) if h in hours)
        if scored < MIN_SCORED_HOURS:
            continue
        peak_hour = max(hours, key=lambda h: hours[h])
        if peak_hour <= 2:
            continue  # front-loaded global unlock: wrong shape family
        base = 2.0 if "PC" not in comp.get("platforms", "") else 1.0
        curves.append(
            {
                "base_weight": base,
                "v1": v1,
                "peak_hour": peak_hour,
                "lr": {h: math.log(hours[h] / v1) for h in range(2, 25) if h in hours},
            }
        )
    return curves


def scale_weight(v1: float, p1: float) -> float:
    """Gaussian kernel in log10 scale around the case's hour-1 print."""
    d = math.log10(v1 / p1) / SCALE_BW_DEX
    return math.exp(-0.5 * d * d)


def weighted_median(pairs: list[tuple[float, float]]) -> float:
    """Median of values with weights (pairs are (value, weight))."""
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    acc = 0.0
    for value, weight in ordered:
        acc += weight
        if acc >= total / 2:
            return value
    return ordered[-1][0]


def weighted_mean(pairs: list[tuple[float, float]]) -> float:
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def weighted_std(pairs: list[tuple[float, float]], mean: float) -> float:
    var = sum(w * (v - mean) ** 2 for v, w in pairs) / sum(w for _, w in pairs)
    return math.sqrt(max(var, 0.0))


def persistence_quantiles(p1: float, hour: int) -> list[float | int]:
    """The house baseline shape: flat at p1, spread widening with the day."""
    return [round2(p1 * math.exp(z * FALLBACK_SIGMA * math.sqrt(hour - 1))) for z in Z]


def hour_quantiles(p1: float, hour: int, curves: list[dict]) -> list[float | int]:
    """Five quantiles for one hour from the weighted comparable curves."""
    pairs = [
        (c["lr"][hour], c["base_weight"] * scale_weight(c["v1"], p1))
        for c in curves
        if hour in c["lr"]
    ]
    pairs = [(v, w) for v, w in pairs if w > 0]
    if len(pairs) < MIN_CURVES_PER_HOUR:
        return persistence_quantiles(p1, hour)
    median = weighted_median(pairs)
    spread = weighted_std(pairs, weighted_mean(pairs))
    sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, SIGMA_MULT * spread))
    quantiles = sorted(
        max(1.0, min(1e9, p1 * math.exp(median + z * sigma))) for z in Z
    )
    return [round2(q) for q in quantiles]


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])
    curves = comparable_curves(case)
    return {
        "hours": [
            {"hour": row["hour"], "q": hour_quantiles(p1, row["hour"], curves)}
            for row in case["forecast"]
        ]
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
