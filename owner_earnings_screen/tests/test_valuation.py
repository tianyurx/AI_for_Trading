import math
import unittest

from owner_earnings_screen import valuation as V


class WashingtonPost1973(unittest.TestCase):
    """Reproduce the published arithmetic, $ millions."""
    NI, DA, CAPEX, RF = 13.3, 3.7, 6.6, 0.0681

    def test_step1_owner_earnings(self):
        oe = V.owner_earnings(self.NI, self.DA, self.CAPEX)
        self.assertAlmostEqual(oe, 10.4, places=6)
        self.assertAlmostEqual(V.capitalise(oe, self.RF), 152.7, places=1)

    def test_steps_2_and_3(self):
        oe = V.owner_earnings(self.NI, self.DA, self.CAPEX)
        v = V.four_steps(oe, self.NI, self.RF, franchise=True, ratio=1.5)
        self.assertAlmostEqual(v["v2"], 195.3, places=1)
        self.assertAlmostEqual(v["v3"], 349.1, places=1)   # 13.3 / 3.81%
        self.assertAlmostEqual(v["v4"], v["v3"] * 1.5)
        self.assertAlmostEqual(v["v_low"], v["v1"])        # conservative end = step 1

    def test_price_was_below_no_growth_value(self):
        oe = V.owner_earnings(self.NI, self.DA, self.CAPEX)
        self.assertLess(V.implied_growth(oe, 80.0, self.RF), 0)


class Guards(unittest.TestCase):
    def test_cap_rate_floor_at_todays_yields(self):
        self.assertAlmostEqual(V.franchise_cap_rate(0.0681), 0.0381)
        self.assertAlmostEqual(V.franchise_cap_rate(0.045), 0.0381)   # not 1.5%

    def test_margin_ratio_is_symmetric_and_clipped(self):
        self.assertAlmostEqual(V.margin_ratio(0.15, 0.10), 1.5)
        self.assertAlmostEqual(V.margin_ratio(0.10, 0.20), 0.5)
        self.assertAlmostEqual(V.margin_ratio(0.30, 0.10), 1.5)       # clipped
        self.assertTrue(math.isnan(V.margin_ratio(0.10, -0.02)))

    def test_peak_margins_lower_the_conservative_value(self):
        v = V.four_steps(oe=100, ni=100, rate=0.05, ratio=0.5)
        self.assertAlmostEqual(v["v_low"], 1000)   # half of 2000
        self.assertAlmostEqual(v["v_high"], 2000)

    def test_depressed_margins_do_not_raise_the_conservative_value(self):
        v = V.four_steps(oe=100, ni=100, rate=0.05, ratio=1.5)
        self.assertAlmostEqual(v["v_low"], 2000)
        self.assertAlmostEqual(v["v_high"], 3000)

    def test_capex_heavy_business_is_capped_by_step1(self):
        v = V.four_steps(oe=-50, ni=100, rate=0.05)
        self.assertLess(v["v_low"], 0)


if __name__ == "__main__":
    unittest.main()
