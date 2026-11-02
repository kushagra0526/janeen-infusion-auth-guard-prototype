"""Infusion-day authorization guard.

For every scheduled infusion, check it against the patient's prior
authorizations before the drug is mixed: date window, product (HCPCS),
billing units including vial waste, visit count, weight-based dose,
site of care, and renewal lead time. Output INFUSE / HOLD / RENEW per visit.
"""
from __future__ import annotations

import math
from itertools import product
from dataclasses import dataclass, field
from datetime import date, timedelta

# HCPCS code -> (drug, mg per billing unit, vial sizes in mg)
CODES = {
    "J1745": ("infliximab (Remicade)", 10, (100,)),
    "Q5103": ("infliximab-dyyb (Inflectra)", 10, (100,)),
    "Q5104": ("infliximab-abda (Renflexis)", 10, (100,)),
    "Q5121": ("infliximab-axxq (Avsola)", 10, (100,)),
    "J3380": ("vedolizumab (Entyvio)", 1, (300,)),
    "J2350": ("ocrelizumab (Ocrevus)", 1, (300,)),
    "J0129": ("abatacept (Orencia)", 10, (250,)),
    "J3262": ("tocilizumab (Actemra)", 1, (80, 200, 400)),
}


@dataclass
class Auth:
    id: str
    patient: str
    hcpcs: str
    start: date
    end: date
    units: int                 # approved billing units for the whole window
    visits: int
    dose_mg_per_kg: float | None   # None = flat dose
    flat_mg: float | None
    site: str                  # office | home | hospital_outpatient
    counts_waste: bool = True  # payer counts JW-modifier waste against approved units


@dataclass
class Visit:
    id: str
    patient: str
    on: date
    hcpcs: str
    weight_kg: float | None
    dose_mg_per_kg: float | None
    flat_mg: float | None
    site: str


@dataclass
class Result:
    visit: str
    action: str                # INFUSE | HOLD | RENEW
    reasons: list[str] = field(default_factory=list)
    auth: str | None = None
    units: int = 0


def dose_mg(v: Visit) -> float:
    return v.flat_mg if v.flat_mg is not None else v.dose_mg_per_kg * v.weight_kg


def vials(code: str, mg: float) -> tuple[float, int]:
    """Smallest amount drawable from whole vials, and the mg wasted."""
    sizes = CODES[code][2]
    cap = math.ceil(mg / min(sizes))
    drawn = min(sum(c * s for c, s in zip(combo, sizes))
                for combo in product(range(cap + 1), repeat=len(sizes))
                if sum(c * s for c, s in zip(combo, sizes)) >= mg - 1e-9)
    return drawn, int(round(drawn - mg))


def units(code: str, mg: float, with_waste: bool) -> int:
    per = CODES[code][1]
    drawn, _ = vials(code, mg)
    return math.ceil((drawn if with_waste else mg) / per)


def guard(visits: list[Visit], auths: list[Auth], renew_lead_days: int = 14,
          weight_tolerance: float = 0.10) -> list[Result]:
    out = []
    used: dict[str, list[int]] = {}   # auth id -> [units, visits]
    for v in sorted(visits, key=lambda x: (x.on, x.id)):
        mine = [a for a in auths if a.patient == v.patient]
        if not mine:
            out.append(Result(v.id, "HOLD", ["NO_AUTH: no authorization on file for this patient"]))
            continue
        same_code = [a for a in mine if a.hcpcs == v.hcpcs]
        covering = [a for a in same_code if a.start <= v.on <= a.end]
        if not covering:
            reasons = []
            other = [a for a in mine if a.start <= v.on <= a.end]
            if other:
                a = other[0]
                reasons.append(f"PRODUCT: auth {a.id} covers {a.hcpcs} {CODES[a.hcpcs][0]}, visit is {v.hcpcs} {CODES[v.hcpcs][0]}")
            elif same_code:
                a = max(same_code, key=lambda x: x.end)
                if v.on > a.end:
                    reasons.append(f"EXPIRED: auth {a.id} ended {a.end:%d %b %Y}")
                else:
                    reasons.append(f"NOT_YET: auth {a.id} starts {a.start:%d %b %Y}")
            else:
                reasons.append(f"NO_AUTH: nothing on file for {v.hcpcs}")
            out.append(Result(v.id, "HOLD", reasons))
            continue
        a = covering[0]
        reasons = []
        mg = dose_mg(v)
        u = units(v.hcpcs, mg, a.counts_waste)
        tally = used.setdefault(a.id, [0, 0])
        if a.dose_mg_per_kg is not None:
            if v.dose_mg_per_kg is None or v.dose_mg_per_kg > a.dose_mg_per_kg + 1e-9:
                reasons.append(f"DOSE: ordered {v.dose_mg_per_kg} mg/kg, auth {a.id} approves {a.dose_mg_per_kg} mg/kg")
        elif a.flat_mg is not None and mg > a.flat_mg + 1e-9:
            reasons.append(f"DOSE: ordered {mg:g} mg, auth {a.id} approves {a.flat_mg:g} mg")
        if tally[0] + u > a.units:
            reasons.append(f"UNITS: this visit needs {u} units ({mg:.0f} mg"
                           + (f" + {vials(v.hcpcs, mg)[1]} mg waste" if a.counts_waste and vials(v.hcpcs, mg)[1] else "")
                           + f"); {a.units - tally[0]} of {a.units} left on {a.id}")
        if tally[1] + 1 > a.visits:
            reasons.append(f"VISITS: {a.visits} visits approved on {a.id}, this is visit {tally[1] + 1}")
        if v.site != a.site:
            reasons.append(f"SITE: auth {a.id} is for {a.site}, visit is at {v.site}")
        if reasons:
            out.append(Result(v.id, "HOLD", reasons, a.id, u))
            continue
        tally[0] += u
        tally[1] += 1
        res = Result(v.id, "INFUSE", [], a.id, u)
        nxt = [w for w in visits if w.patient == v.patient and w.on > v.on]
        if nxt:
            n = min(nxt, key=lambda w: w.on)
            covered_next = any(b.hcpcs == n.hcpcs and b.start <= n.on <= b.end for b in mine)
            if not covered_next and n.on > a.end:
                res.action = "RENEW"
                res.reasons.append(f"RENEW: next infusion {n.on:%d %b} is after {a.id} ends {a.end:%d %b}; "
                                   f"submit renewal by {n.on - timedelta(days=renew_lead_days):%d %b}")
        out.append(res)
    return out


def tracker_baseline(visits: list[Visit], auths: list[Auth]) -> dict[str, bool]:
    """A spreadsheet check: same patient, same drug name, date inside the window."""
    ok = {}
    for v in visits:
        drug = CODES[v.hcpcs][0].split()[0].split("-")[0]
        ok[v.id] = any(a.patient == v.patient and CODES[a.hcpcs][0].split()[0].split("-")[0] == drug
                       and a.start <= v.on <= a.end for a in auths)
    return ok
