"""gta6-twitch-ccu-forecast-01 entry: a comparable-launches quantile forecaster.

Model in one paragraph: a big launch's release-day Twitch curve, hour by hour, looks like
other big launches' release-day curves once each is divided by its own first hour. So for
every past launch in the case's `comparables` whose release day is fully recorded, take
the log-ratios r_h = ln(v_h) - ln(v_1) for h = 2..24. The forecast for hour h is the case's
own hour-1 print p1 times exp(q_tau({r_h})), where q_tau blends the empirical tau-quantile
of the ratios with a normal fit (weighted mean, weighted sd) of the same ratios, 50/50 in
log space. Comparables are weighted by the similarity of their hour-1 viewer scale to the
target's, a kernel whose bandwidth was chosen by leave-one-out validation over the
comparables themselves (see README.md). A second kernel, on the anticipation scale of
each launch's main trailer (figures vendored below as constants, because the sandbox has
no network), was tested the same way and rejected: it raised the loss overall and on the
trailer-known targets alike, so it ships switched off.

Runs as the grader runs it: `python3 -P -s /bot/main.py`, Python 3.13 standard library
only, no network, deterministic (two runs on a case write the same bytes), far under the
8-second cap. Reads every <id>.in in $MAKEFUN_INPUT_DIR (else /input) and writes
<id>.out to $MAKEFUN_OUTPUT_DIR (else /output).
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, as the starter does.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level (full precision, not the starter's rounding).
Z = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]
HOURS = list(range(2, 25))

# --- Calibration knobs (set by leave-one-out validation; see README.md) ----------------
# Each knob's neutral value switches it off. SCALE_S / TRAILER_S are the bandwidth, in
# natural-log units, of the similarity kernels w = exp(-|ln(a/b)| / s) applied to the
# hour-1 viewer scale and to the trailer-view scale; None disables that kernel.
# INFLATE multiplies each quantile's log-deviation from the blended median; SHRINK
# multiplies the blended median log-ratio (pulling the whole curve toward persistence).
#
# LOO verdicts (148 pseudo-targets = the 37 usable comparables x the 4 practice cases,
# which share one comparable pool; persistence LOO loss 0.9296, unweighted model 0.7316):
# the hour-1 scale kernel at s = 0.75 is the one knob that earns its place, cutting the
# loss to 0.4109: a launch's first-hour scale encodes its unlock geometry (a small hour 1
# means most regions have not unlocked yet and the surge is still coming), so launches of
# a similar scale share a curve shape. The trailer kernel never helped: alone it scored
# 0.7338-0.7366, and on top of the scale kernel it worsened both the overall loss
# (0.4115-0.4138 against 0.4109-0.4123) and the loss on the trailer-known targets
# themselves, so TRAILER_S stays off and no trailer-based shape tilt is baked in either.
# INFLATE and SHRINK likewise never beat their neutral values on top of the scale kernel.
SCALE_S = 0.75
TRAILER_S = None
INFLATE = 1.0
SHRINK = 1.0

# --- Trailer anticipation scale, vendored ----------------------------------------------
# The main (reveal) trailer's YouTube views, in millions, best documented figure found in
# November 2026 press/analyst reporting (sources in README.md). The sandbox has no
# network, so the figures ship as constants. They enter only through a log-scale
# similarity kernel, so a factor-of-two error in any one figure barely moves a weight.
# A launch with no entry gets no trailer weight (factor 1), never a guessed figure.
# Keys are normalized names: upper case, letters and digits only.
TRAILER_VIEWS_M = {
    "GRANDTHEFTAUTO VI": 300.0,  # Trailer 1 (Dec 2023): 93M in 24 h, ~302M lifetime
    "GRANDTHEFTAUTO6": 300.0,
    "REDDEADREDEMPTION2": 30.0,  # announcement trailer, ~30.5M lifetime
    "CYBERPUNK2077": 25.0,  # E3 2018 trailer, >25M by Aug 2018 (CD Projekt Red)
    "ELDENRING": 10.0,  # gameplay reveal, 10.2M+ across uploads (Benji-Sales, Jun 2021)
    "MARVELSSPIDERMAN2": 26.0,  # reveal trailer, 20M+ by Jan 2022, ~26M by Dec 2022
    "GODOFWARRAGNAROK": 10.0,  # gameplay reveal, 10M+ in 24 h (Benji-Sales, Sep 2021)
    "GODOFWARRAGNARÖK": 10.0,
    "HOGWARTSLEGACY": 30.0,  # reveal trailer, 28M by Mar 2022 (PlayStation Blog)
    "STARFIELD": 14.0,  # teaser trailer, 9.2M Bethesda + 4.6M Xbox channels, Jun 2021
    "MARATHON": 13.0,  # reveal, 13M+ in 24 h (Benji-Sales, May 2023)
    "CALLOFDUTYMODERNWARFAREIII": 15.0,  # reveal trailer, ~15M in 11 days (Aug 2023)
    "THELEGENDOFZELDATEARSOFKINGDOM": 6.0,  # announcement teaser, 6.4M (E3 2021 tally)
    "FORZAHORIZON5": 4.0,  # reveal, 4.2M across uploads (E3 2021 tally)
}


def norm_name(name: str) -> str:
    """A comparable/game name reduced to upper-case letters and digits for lookup."""
    return "".join(ch for ch in name.upper() if ch.isalnum())


def trailer_views(name: str) -> float | None:
    return TRAILER_VIEWS_M.get(norm_name(name))


def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def day_curve(comparable: dict) -> dict[int, float] | None:
    """The comparable's release-day curve {hour 1..24: viewers}, or None if unusable.

    Unusable: any of the day's 24 hours missing, or any hour's viewers not positive
    (hour 1 anchors every ratio, and a zero inside the day would poison its log).
    """
    try:
        start = parse_ts(comparable["day_start"])
    except (KeyError, ValueError):
        return None
    curve: dict[int, float] = {}
    for row in comparable.get("hourly", []):
        try:
            at = parse_ts(row["from"])
        except (KeyError, ValueError, TypeError):
            continue
        delta = (at - start).total_seconds()
        if 0 <= delta < 24 * 3600 and delta % 3600 == 0:
            viewers = row.get("viewers")
            if isinstance(viewers, (int, float)) and viewers > 0:
                curve[int(delta // 3600) + 1] = float(viewers)
    if len(curve) != 24:
        return None
    return curve


def weighted_quantile(sorted_pairs: list[tuple[float, float]], tau: float) -> float:
    """The tau-quantile of values with weights, by linear interpolation on the CDF.

    sorted_pairs: (value, weight) sorted by value, weights positive. The empirical CDF
    steps at each value's midpoint mass; interpolating between the bracketing points
    keeps the result continuous in tau and deterministic.
    """
    total = sum(w for _, w in sorted_pairs)
    target = tau * total
    acc = 0.0
    prev_value = sorted_pairs[0][0]
    prev_acc = 0.0
    for value, weight in sorted_pairs:
        acc += weight
        if acc >= target:
            if acc == prev_acc:
                return value
            frac = (target - prev_acc) / (acc - prev_acc)
            return prev_value + frac * (value - prev_value)
        prev_value, prev_acc = value, acc
    return sorted_pairs[-1][0]


def hour_forecast(ratios: list[tuple[float, float]]) -> list[float]:
    """The five log-quantiles of one hour from (log-ratio, weight) pairs.

    Blends the weighted empirical quantile with the weighted normal fit 50/50 in log
    space, then applies the INFLATE knob around the blended median.
    """
    pairs = sorted(ratios)
    total_w = sum(w for _, w in pairs)
    mean = sum(r * w for r, w in pairs) / total_w
    var = sum(w * (r - mean) ** 2 for r, w in pairs) / total_w
    sd = math.sqrt(var)
    logs = []
    for tau, z in zip(LEVELS, Z):
        empirical = weighted_quantile(pairs, tau)
        normal = mean + z * sd
        logs.append(0.5 * empirical + 0.5 * normal)
    median = logs[2]
    return [median + INFLATE * (value - median) for value in logs]


def comparable_weight(
    target_p1: float,
    target_trailer: float | None,
    comp_v1: float,
    comp_trailer: float | None,
) -> float:
    """The similarity weight of one comparable for this target; 1.0 when a kernel is off."""
    weight = 1.0
    if SCALE_S is not None:
        weight *= math.exp(-abs(math.log(target_p1 / comp_v1)) / SCALE_S)
    if TRAILER_S is not None and target_trailer is not None and comp_trailer is not None:
        weight *= math.exp(-abs(math.log(target_trailer / comp_trailer)) / TRAILER_S)
    return weight


def persistence_quantiles(p1: float, h: int) -> list[float]:
    """The house baseline's row for hour h, the fallback when no comparable is usable."""
    return [p1 * math.exp(z * 0.15 * math.sqrt(h - 1)) for z in Z]


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up, as the starter rounds (whole numbers as ints)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def forecast_case(case: dict) -> dict:
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    target_trailer = trailer_views(case.get("game", {}).get("name", ""))

    # The pool: one (log-ratio by hour, weight) per usable comparable.
    pool: list[tuple[dict[int, float], float]] = []
    for comparable in case.get("comparables", []):
        curve = day_curve(comparable)
        if curve is None:
            continue
        v1 = curve[1]
        weight = comparable_weight(p1, target_trailer, v1, trailer_views(comparable.get("name", "")))
        ratios = {h: math.log(curve[h]) - math.log(v1) for h in HOURS}
        pool.append((ratios, weight))

    rows = []
    for row in case["forecast"]:
        h = row["hour"]
        if pool:
            log_q = hour_forecast([(ratios[h], w) for ratios, w in pool])
            median = log_q[2]
            log_q = [median * SHRINK + (value - median) for value in log_q] if SHRINK != 1.0 else log_q
            quantiles = [p1 * math.exp(value) for value in log_q]
        else:
            quantiles = persistence_quantiles(p1, h)
        # The contract: five finite numbers, 0 < q <= 1e9, non-decreasing.
        cleaned: list[float] = []
        for q in quantiles:
            q = min(max(q, 1e-6), 1e9)
            if cleaned and q < cleaned[-1]:
                q = cleaned[-1]
            cleaned.append(q)
        rows.append({"hour": h, "q": [round2(q) for q in cleaned]})
    return {"hours": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
