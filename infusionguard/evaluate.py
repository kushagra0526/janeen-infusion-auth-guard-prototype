"""Score the guard. Usage: python -m infusionguard.evaluate dev|heldout"""
from __future__ import annotations

import json
import sys
from collections import Counter

from .gen import clinic
from .guard import guard, tracker_baseline

SEEDS = {"dev": range(0, 40), "heldout": range(7000, 7060)}


def run(split):
    caught, total, base_caught = Counter(), Counter(), Counter()
    clean = clean_held = clean_base_held = 0
    renew_hit = renew_total = 0
    wrong_reason, examples = 0, []
    for seed in SEEDS[split]:
        c = clinic(seed, split)
        res = {r.visit: r for r in guard(c["visits"], c["auths"])}
        base = tracker_baseline(c["visits"], c["auths"])
        for v in c["visits"]:
            want = c["truth"].get(v.id)
            r = res[v.id]
            codes = {x.split(":")[0] for x in r.reasons}
            if want:
                total[want] += 1
                ok = r.action == "HOLD" and want in codes
                caught[want] += ok
                base_caught[want] += not base[v.id]
                if r.action == "HOLD" and want not in codes:
                    wrong_reason += 1
                if not ok and len(examples) < 8:
                    examples.append({"want": want, "got": r.action, "reasons": r.reasons, "visit": v.id})
            else:
                clean += 1
                clean_held += r.action == "HOLD"
                clean_base_held += not base[v.id]
                if r.action == "HOLD" and len(examples) < 8:
                    examples.append({"false_hold": r.reasons, "visit": v.id})
            if f"renew:{v.id}" in c["truth"]:
                renew_total += 1
                renew_hit += r.action == "RENEW"
    return {"split": split, "problems": {k: f"{caught[k]}/{total[k]}" for k in sorted(total)},
            "problems_total": f"{sum(caught.values())}/{sum(total.values())}",
            "tracker_baseline": f"{sum(base_caught.values())}/{sum(total.values())}",
            "tracker_by_kind": {k: f"{base_caught[k]}/{total[k]}" for k in sorted(total)},
            "held_for_other_reason": wrong_reason,
            "clean_visits": clean, "clean_held": clean_held, "clean_held_tracker": clean_base_held,
            "renewal_flagged_before_lapse": f"{renew_hit}/{renew_total}", "examples": examples}


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1] if len(sys.argv) > 1 else "dev"), indent=1, default=str))
