# Infusion-day authorization guard (Janeen / Ruma Care)

**Unofficial prototype by Kushagra Pratap Singh. Not affiliated with Janeen (formerly Ruma Care).**

## The problem
Janeen's launch post: biologics cost $80–150K+ per patient per year, clinics buy them up front, and "when workflows fail, or patients are infused before paperwork is cleared, providers don't get reimbursed for the medication" ([YC page](https://www.ycombinator.com/companies/janeen)). Getting the prior auth approved is half the job. The other half is the infusion chair: an approved auth only pays for the product, dose, units, visits, dates and site it names. Clinics usually track that in a spreadsheet: *same patient, same drug, date inside the window*.

## What I built
A check that runs on the schedule before the drug is mixed. Each visit gets **INFUSE / HOLD / RENEW** with the reason:

| Code | Catches |
|---|---|
| `PRODUCT` | auth names one HCPCS product (Inflectra Q5103) and the clinic stocked another (Remicade J1745) — same molecule, different code |
| `DOSE` | escalation (5 → 10 mg/kg) or a weight-based flat dose over the approved mg |
| `UNITS` | billing units incl. vial waste (JW) when the payer counts it, running total against approved units; weight gain pushes a dose over |
| `VISITS` | more infusions than approved (shortened interval) |
| `SITE` | auth for office/home, visit booked at hospital outpatient |
| `EXPIRED / NOT_YET / NO_AUTH` | date outside every window for that product |
| `RENEW` | next infusion falls after the auth ends with no renewal on file → submit by (next date − 14 days) |

A held visit consumes no units, so later visits are judged against what is really left. Codes and units: infliximab J1745 and biosimilars Q5103/Q5104/Q5121 (10 mg/unit, 100 mg vials), vedolizumab J3380, ocrelizumab J2350, abatacept J0129, tocilizumab J3262 (80/200/400 mg vials).

## Demo (`python demo.py`)
```
chair-1   Maria R.  J1745 infliximab (Remicade)      HOLD    tracker: ok
            PRODUCT: auth PA-1041 covers Q5103 infliximab-dyyb (Inflectra), visit is J1745 infliximab (Remicade)
chair-2   James T.  Q5103 infliximab-dyyb (Inflectra) HOLD   tracker: ok
            DOSE: ordered 10.0 mg/kg, auth PA-1077 approves 5.0 mg/kg
chair-3   Aiko N.   J3380 vedolizumab (Entyvio)      RENEW   tracker: ok
            RENEW: next infusion 13 Jan is after PA-1102 ends 30 Nov; submit renewal by 30 Dec
chair-4   Dev P.    Q5121 infliximab-axxq (Avsola)   HOLD    tracker: ok
            UNITS: this visit needs 50 units (480 mg + 20 mg waste); 40 of 40 left on PA-1110
chair-5   Lena K.   J2350 ocrelizumab (Ocrevus)      HOLD    tracker: ok
            SITE: auth PA-1123 is for office, visit is at hospital_outpatient
chair-6   Omar S.   J3262 tocilizumab (Actemra)      HOLD    tracker: ok
            DOSE: ordered 704 mg, auth PA-1131 approves 640 mg
```
The spreadsheet check passes all six.

## Results (synthetic clinics, known truth)
26-week schedules for 30–50 patients (dev) / 60–90 (held-out) on real regimens (infliximab q8w 5 mg/kg, vedolizumab 300 mg q8w, ocrelizumab 600 mg q26w, abatacept weight tiers q4w, tocilizumab 8 mg/kg q4w max 800 mg), one auth each, 70% of payers counting waste, and planted problems. Held-out adds look-alikes that must pass (switch with a new auth for the new product, back-to-back renewal, weight loss, payers not counting waste) and was committed to git before its first run.

| | dev (40 clinics) | held-out (60 clinics, first run) |
|---|---|---|
| problem infusions held, right reason | 1,284 / 1,284 | **2,503 / 2,503** |
| … by the spreadsheet check | 751 / 1,284 | 1,489 / 2,503 |
| clean infusions held | 0 / 4,417 | **0 / 14,169** |
| renewals flagged before the lapse | 112 / 112 | 185 / 185 |

The spreadsheet check misses every PRODUCT, DOSE, UNITS, VISITS and SITE problem (1,014 held-out infusions).

## Honest limits
- **Circular by construction.** The generator and the guard use the same unit and vial arithmetic and the same rules; 100% shows the rules are applied consistently, not that they match every payer. The real work is per-payer rules (waste, site-of-care lists, dose tolerance), which I made parameters, not data.
- Dev fixes before the numbers above were in the generator's truth labels (only the first escalated / over-unit visit was labelled; later ones are problems too). The guard was not changed. One unit test had a wrong expected number (forgot vial waste) and was corrected after the held-out run.
- Not modelled: units per date-of-service limits, loading doses (weeks 0-2-6), J-code crosswalk changes, pharmacy-benefit (white/brown bagging), NDC on claims, patient copay programs.
- Not clinical or billing advice.

## Run it (Python 3.10+, stdlib only)
```
python demo.py
python -m unittest discover -s tests -t .
python -m infusionguard.evaluate heldout
```
