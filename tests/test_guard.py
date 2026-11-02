import unittest
from datetime import date

from infusionguard.guard import Auth, Visit, guard, tracker_baseline, units, vials


def auth(**kw):
    base = dict(id="A1", patient="P1", hcpcs="Q5103", start=date(2026, 11, 1), end=date(2027, 4, 30), units=140,
                visits=4, dose_mg_per_kg=5.0, flat_mg=None, site="office", counts_waste=True)
    base.update(kw)
    return Auth(**base)


def visit(vid="v1", on=date(2026, 11, 10), **kw):
    base = dict(patient="P1", hcpcs="Q5103", weight_kg=70.0, dose_mg_per_kg=5.0, flat_mg=None, site="office")
    base.update(kw)
    return Visit(vid, on=on, **base)


class Units(unittest.TestCase):
    def test_vial_waste_counts_when_payer_counts_it(self):
        self.assertEqual(vials("Q5103", 350), (400, 50))
        self.assertEqual(units("Q5103", 350, True), 40)
        self.assertEqual(units("Q5103", 350, False), 35)
        self.assertEqual(vials("J3262", 560), (560, 0))   # 400 + 80 + 80


class Guard(unittest.TestCase):
    def test_clean_visit_infuses(self):
        self.assertEqual(guard([visit()], [auth()])[0].action, "INFUSE")

    def test_biosimilar_swap_is_held_but_tracker_passes_it(self):
        v = visit(hcpcs="J1745")
        r = guard([v], [auth()])[0]
        self.assertEqual((r.action, r.reasons[0].split(":")[0]), ("HOLD", "PRODUCT"))
        self.assertTrue(tracker_baseline([v], [auth()])["v1"])

    def test_dose_escalation_site_and_units(self):
        self.assertIn("DOSE", guard([visit(dose_mg_per_kg=10.0)], [auth()])[0].reasons[0])
        self.assertIn("SITE", guard([visit(site="hospital_outpatient")], [auth()])[0].reasons[0])
        r = guard([visit(weight_kg=100.0)], [auth(units=40)])[0]
        self.assertTrue(r.reasons[0].startswith("UNITS"))

    def test_renewal_flagged_before_lapse_and_expiry_held(self):
        vs = [visit("v1", date(2026, 11, 10)), visit("v2", date(2027, 1, 5))]
        rs = guard(vs, [auth(end=date(2026, 12, 31))])
        self.assertEqual([r.action for r in rs], ["RENEW", "HOLD"])
        self.assertIn("by 22 Dec", rs[0].reasons[0])
        self.assertTrue(rs[1].reasons[0].startswith("EXPIRED"))

    def test_held_visit_does_not_consume_units(self):
        vs = [visit("v1", date(2026, 11, 10), site="home"), visit("v2", date(2026, 12, 10))]
        rs = guard(vs, [auth(units=35, visits=1)])
        self.assertEqual([r.action for r in rs], ["HOLD", "INFUSE"])


if __name__ == "__main__":
    unittest.main()
