"""Synthetic infusion clinic: patients, authorizations, 26-week schedule, planted problems."""
from __future__ import annotations

import random
from datetime import date, timedelta

from .guard import Auth, Visit, dose_mg, units

# hcpcs, every N weeks, dosing (mg/kg or flat), max mg
REGIMENS = [("Q5103", 8, 5.0, None), ("J1745", 8, 5.0, None), ("Q5121", 8, 5.0, None), ("Q5104", 8, 5.0, None),
            ("J3380", 8, None, 300.0), ("J2350", 26, None, 600.0), ("J0129", 4, None, None), ("J3262", 4, 8.0, None)]
INFLIX = ["J1745", "Q5103", "Q5104", "Q5121"]
SITES = ["office", "office", "office", "home"]


def abatacept_mg(kg):
    return 500.0 if kg < 60 else (750.0 if kg <= 100 else 1000.0)


def make_visit(vid, pid, on, code, kg, per_kg, flat, site):
    if code == "J0129":
        flat = abatacept_mg(kg)
    if code == "J3262":
        flat, per_kg = min(800.0, 8.0 * kg), None
    return Visit(vid, pid, on, code, kg, per_kg, flat, site)


def clinic(seed: int, split: str = "dev"):
    rng = random.Random(seed)
    today = date(2026, 11, 2) + timedelta(days=rng.randint(0, 60))
    n_pat = rng.randint(30, 50) if split == "dev" else rng.randint(60, 90)
    auths, visits, truth = [], [], {}
    kinds = ["clean"] * 5 + ["expired", "product", "escalate", "weight_gain", "site", "interval", "no_auth",
                             "not_yet", "renew_due"]
    if split == "heldout":
        kinds += ["clean_switch", "clean_renewed", "weight_loss", "waste_payer"] * 2
    for i in range(n_pat):
        pid = f"P{seed:04d}-{i:03d}"
        code, every, per_kg, flat = rng.choice(REGIMENS)
        kg = round(rng.uniform(48, 118), 1)
        site = rng.choice(SITES)
        start = today - timedelta(weeks=rng.randint(0, 6))
        n = max(2, 26 // every)
        sched = [start + timedelta(weeks=every * k) for k in range(n)]
        vs = [make_visit(f"{pid}-v{k}", pid, d, code, kg, per_kg, flat, site) for k, d in enumerate(sched)]
        waste = rng.random() < 0.7
        need = sum(units(code, dose_mg(v), waste) for v in vs)
        a = Auth(f"A-{pid}", pid, code, start - timedelta(days=rng.randint(1, 20)), sched[-1] + timedelta(days=rng.randint(3, 20)),
                 need, len(vs), per_kg if code not in ("J0129", "J3262") else None,
                 None if (per_kg and code != "J3262") else max(dose_mg(v) for v in vs), site, waste)
        if code == "J3262":
            a.dose_mg_per_kg, a.flat_mg = None, max(dose_mg(v) for v in vs)
        kind = rng.choice(kinds)
        bad = {}
        k = rng.randrange(1, len(vs))
        if kind == "expired":
            a.end = vs[k].on - timedelta(days=rng.randint(1, 10))
            a.visits, a.units = k, sum(units(code, dose_mg(v), waste) for v in vs[:k])
            bad = {v.id: "EXPIRED" for v in vs[k:]}
        elif kind == "renew_due":
            a.end = vs[-2].on + timedelta(days=rng.randint(1, 5))
            a.visits = len(vs) - 1
            a.units = sum(units(code, dose_mg(v), waste) for v in vs[:-1])
            bad = {vs[-1].id: "EXPIRED"}
            truth[f"renew:{vs[-2].id}"] = True
        elif kind == "product" and code in INFLIX:
            other = rng.choice([c for c in INFLIX if c != code])
            for v in vs[k:]:
                v.hcpcs = other
            bad = {v.id: "PRODUCT" for v in vs[k:]}
        elif kind == "escalate" and per_kg and code in INFLIX:
            for v in vs[k:]:
                v.dose_mg_per_kg = 10.0
            bad = {v.id: "DOSE" for v in vs[k:]}
        elif kind == "weight_gain" and code in INFLIX + ["J3262"]:
            for v in vs[k:]:
                nv = make_visit(v.id, pid, v.on, code, round(kg * rng.uniform(1.15, 1.3), 1), v.dose_mg_per_kg, v.flat_mg, site)
                v.weight_kg, v.flat_mg = nv.weight_kg, nv.flat_mg
            if code == "J3262":
                bad = {v.id: "DOSE" for v in vs if dose_mg(v) > a.flat_mg + 1e-9}
            else:
                # a held visit consumes nothing, so every visit after the first overrun is short too
                used, over = 0, False
                for v in vs:
                    u = units(code, dose_mg(v), waste)
                    if over or used + u > a.units:
                        over = True
                        bad[v.id] = "UNITS"
                    else:
                        used += u
        elif kind == "site":
            for v in vs[k:]:
                v.site = "hospital_outpatient"
            bad = {v.id: "SITE" for v in vs[k:]}
        elif kind == "interval" and every >= 8:
            extra = make_visit(f"{pid}-x", pid, vs[k].on - timedelta(weeks=2), code, kg, per_kg, flat, site)
            vs.append(extra)
            vs.sort(key=lambda v: v.on)
            # the extra visit uses a slot; the last scheduled visit has nothing left
            bad = {vs[-1].id: "VISITS"}
        elif kind == "no_auth":
            a = None
            bad = {v.id: "NO_AUTH" for v in vs}
        elif kind == "not_yet":
            a.start = vs[0].on + timedelta(days=rng.randint(1, 6))
            bad = {vs[0].id: "NOT_YET"}
        elif kind == "clean_switch" and code in INFLIX:
            other = rng.choice([c for c in INFLIX if c != code])
            a.end = vs[k].on - timedelta(days=1)
            a.visits, a.units = k, sum(units(code, dose_mg(v), waste) for v in vs[:k])
            for v in vs[k:]:
                v.hcpcs = other
            auths.append(Auth(f"A2-{pid}", pid, other, vs[k].on - timedelta(days=3), vs[-1].on + timedelta(days=10),
                              sum(units(other, dose_mg(v), waste) for v in vs[k:]), len(vs) - k, a.dose_mg_per_kg,
                              a.flat_mg, site, waste))
        elif kind == "clean_renewed":
            a.end = vs[k].on - timedelta(days=1)
            a.visits, a.units = k, sum(units(code, dose_mg(v), waste) for v in vs[:k])
            auths.append(Auth(f"A2-{pid}", pid, code, a.end + timedelta(days=1), vs[-1].on + timedelta(days=10),
                              sum(units(code, dose_mg(v), waste) for v in vs[k:]), len(vs) - k, a.dose_mg_per_kg,
                              a.flat_mg, site, waste))
        elif kind == "weight_loss":
            for v in vs[k:]:
                nv = make_visit(v.id, pid, v.on, code, round(kg * 0.88, 1), v.dose_mg_per_kg, v.flat_mg, site)
                v.weight_kg, v.flat_mg = nv.weight_kg, nv.flat_mg
        elif kind == "waste_payer" and not waste:
            pass
        if a:
            auths.append(a)
        visits += vs
        for v in vs:
            truth[v.id] = bad.get(v.id)
    return {"visits": visits, "auths": auths, "truth": truth, "today": today}
