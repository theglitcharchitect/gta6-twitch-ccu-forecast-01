"""Leave-one-out validation over comparables, the scratch harness behind README.md.

For each practice case, each usable comparable in turn plays the target: its release-day
curve is the truth, its hour-1 viewers the given print, and the forecast comes from the
other comparables through main.py's own forecast_case on a synthetic case (so the numbers
grade the shipped code path, knobs included). The score is the contest's: mean pinball
loss on the log scale over hours 2..24 x the five levels. The persistence baseline is
scored the same way. Run: python3 validate.py [kit input dir]
"""

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as model

KIT_INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "~/workspace/makefun-gta6-20261117/gta6-twitch-ccu-forecast-01-kit/input"
).expanduser()

# day_curve is the hot spot (it parses ~400 timestamps per comparable); cache it per dict.
_curve_cache: dict[int, dict | None] = {}
_real_day_curve = model.day_curve


def cached_day_curve(comparable: dict):
    key = id(comparable)
    if key not in _curve_cache:
        _curve_cache[key] = _real_day_curve(comparable)
    return _curve_cache[key]


model.day_curve = cached_day_curve


def pinball(truth: float, quantiles: list[float]) -> float:
    total = 0.0
    ly = math.log(max(truth, 1.0))
    for tau, q in zip(model.LEVELS, quantiles):
        d = ly - math.log(q)
        total += 2.0 * max(tau * d, (tau - 1.0) * d)
    return total / len(model.LEVELS)


def pseudo_case(target: dict, pool: list[dict], target_curve: dict[int, float]) -> dict:
    return {
        "known": [{"hour": 1, "viewers": target_curve[1]}],
        "game": {"name": target.get("name", "")},
        "forecast": [{"hour": h} for h in model.HOURS],
        "comparables": pool,
    }


def loo(configs: dict[str, dict]) -> None:
    # Collect every (case, target) job once; curves are shared across configs.
    jobs = []  # (case_id, target_name, target_curve, pool, target_dict)
    for path in sorted(KIT_INPUT.glob("p*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        comps = case["comparables"]
        curves = [cached_day_curve(c) for c in comps]
        for i, (comp, curve) in enumerate(zip(comps, curves)):
            if curve is None:
                continue
            pool = [c for j, c in enumerate(comps) if j != i]
            jobs.append((case["id"], comp["name"], curve, pool, comp))
    print(f"LOO jobs: {len(jobs)} pseudo-targets across 4 practice cases")
    with_trailer = sum(1 for j in jobs if model.trailer_views(j[1]) is not None)
    print(f"pseudo-targets with a trailer figure: {with_trailer}")

    for label, knobs in configs.items():
        model.SCALE_S = knobs.get("scale")
        model.TRAILER_S = knobs.get("trailer")
        model.INFLATE = knobs.get("inflate", 1.0)
        model.SHRINK = knobs.get("shrink", 1.0)
        started = time.time()
        if label == "persistence":
            total, count = 0.0, 0
            for _, _, curve, _, _ in jobs:
                p1 = curve[1]
                for h in model.HOURS:
                    qs = [model.round2(q) for q in model.persistence_quantiles(p1, h)]
                    total += pinball(curve[h], qs)
                    count += 1
            print(f"{label:28s} loss {total / count:.6f}")
            continue
        total, count = 0.0, 0
        sub_total, sub_count = 0.0, 0  # jobs whose target has a trailer figure
        per_case: dict[str, list[float]] = {}
        for case_id, name, curve, pool, target in jobs:
            forecast = model.forecast_case(pseudo_case(target, pool, curve))
            rows = {row["hour"]: row["q"] for row in forecast["hours"]}
            case_total = 0.0
            for h in model.HOURS:
                case_total += pinball(curve[h], rows[h])
                count += 1
            total += case_total
            if model.trailer_views(name) is not None:
                sub_total += case_total
                sub_count += len(model.HOURS)
            per_case.setdefault(case_id, []).append(case_total / len(model.HOURS))
        detail = "  ".join(
            f"{cid} {sum(v) / len(v):.4f} (n={len(v)})" for cid, v in sorted(per_case.items())
        )
        subset = f"   trailer-targets {sub_total / sub_count:.6f}" if sub_count else ""
        print(f"{label:28s} loss {total / count:.6f}{subset}   [{detail}]   {time.time() - started:.1f}s")


if __name__ == "__main__":
    loo(
        {
            "scale s=0.6": {"scale": 0.6},
            "scale s=0.75": {"scale": 0.75},
            "scale0.75+trailer2.0": {"scale": 0.75, "trailer": 2.0},
            "scale0.75+trailer3.0": {"scale": 0.75, "trailer": 3.0},
            "scale0.75+inflate0.95": {"scale": 0.75, "inflate": 0.95},
            "scale0.75+inflate1.05": {"scale": 0.75, "inflate": 1.05},
            "scale0.75+shrink0.97": {"scale": 0.75, "shrink": 0.97},
        }
    )
