"""Tomorrow's infusion chairs, checked against authorizations. Usage: python demo.py"""
from datetime import date

from infusionguard.guard import CODES, Auth, Visit, guard, tracker_baseline

AUTHS = [
    Auth("PA-1041", "Maria R.", "Q5103", date(2026, 9, 1), date(2027, 2, 28), 160, 4, 5.0, None, "office"),
    Auth("PA-1077", "James T.", "Q5103", date(2026, 8, 15), date(2027, 2, 15), 120, 4, 5.0, None, "office"),
    Auth("PA-1102", "Aiko N.", "J3380", date(2026, 6, 1), date(2026, 11, 30), 900, 3, None, 300.0, "office"),
    Auth("PA-1110", "Dev P.", "Q5121", date(2026, 10, 1), date(2027, 3, 31), 40, 1, 5.0, None, "office"),
    Auth("PA-1123", "Lena K.", "J2350", date(2026, 7, 1), date(2027, 6, 30), 1200, 2, None, 600.0, "office"),
    Auth("PA-1131", "Omar S.", "J3262", date(2026, 10, 1), date(2027, 3, 31), 3840, 6, None, 640.0, "home", False),
]
TOMORROW = date(2026, 11, 18)
VISITS = [
    Visit("chair-1", "Maria R.", TOMORROW, "J1745", 78.0, 5.0, None, "office"),             # clinic stocked Remicade
    Visit("chair-2", "James T.", TOMORROW, "Q5103", 74.0, 10.0, None, "office"),            # escalated to 10 mg/kg
    Visit("chair-3", "Aiko N.", TOMORROW, "J3380", 61.0, None, 300.0, "office"),
    Visit("chair-3b", "Aiko N.", date(2027, 1, 13), "J3380", 61.0, None, 300.0, "office"),  # next dose, after auth ends
    Visit("chair-4", "Dev P.", TOMORROW, "Q5121", 96.0, 5.0, None, "office"),               # weight up from 78 kg: 400 mg was approved
    Visit("chair-5", "Lena K.", TOMORROW, "J2350", 70.0, None, 600.0, "hospital_outpatient"),
    Visit("chair-6", "Omar S.", TOMORROW, "J3262", 88.0, None, 704.0, "home"),              # 8 mg/kg after weight gain
]

if __name__ == "__main__":
    base = tracker_baseline(VISITS, AUTHS)
    for r in guard(VISITS, AUTHS):
        v = next(x for x in VISITS if x.id == r.visit)
        print(f"{v.id:<9} {v.patient:<9} {v.on:%d %b}  {v.hcpcs} {CODES[v.hcpcs][0]:<29} {r.action:<6}"
              f" units {r.units:<4} tracker: {'ok' if base[v.id] else 'flag'}")
        for why in r.reasons:
            print(f"{'':12}{why}")
