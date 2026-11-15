import unittest

import numpy as np
import pandas as pd

from owner_earnings_screen import screen as S

NAN = float("nan")


def history(**overrides):
    """Ten steady fiscal years: 100 of net income, capex equal to D&A."""
    n = 10
    d = {
        "cy": list(range(2016, 2026)),
        "fy_end": pd.to_datetime([f"{y}-12-31" for y in range(2016, 2026)]),
        "ni": [100.0] * n, "ni_total": [NAN] * n, "da": [20.0] * n, "capex": [20.0] * n,
        "cfo": [120.0] * n, "rev": [1000.0] * n, "pretax": [130.0] * n, "opinc": [130.0] * n,
        "sbc": [0.0] * n, "rnd": [NAN] * n, "div": [50.0] * n, "buyback": [30.0] * n,
        "interest": [5.0] * n, "premiums": [NAN] * n, "shares": [10.0] * n, "equity": [500.0] * n,
        "assets": [1000.0] * n,
    }
    d.update(overrides)
    return pd.DataFrame(d)


class CompanyMetrics(unittest.TestCase):
    def test_steady_business(self):
        m = S.company_metrics(history())
        self.assertAlmostEqual(m["ni"], 100)
        self.assertAlmostEqual(m["oe"], 100)
        self.assertAlmostEqual(m["roe_med"], 0.2)
        self.assertAlmostEqual(m["margin_ratio"], 1.0)
        self.assertAlmostEqual(m["payout"], 0.8)
        self.assertTrue(S.is_franchise(m, cyclical=False))
        self.assertFalse(S.is_franchise(m, cyclical=True))

    def test_tax_windfall_is_capped(self):
        ni = [100.0] * 9 + [400.0]              # pre-tax income is still 130
        m = S.company_metrics(history(ni=ni))
        self.assertAlmostEqual(m["ni_reported"], 200)
        self.assertAlmostEqual(m["ni"], (100 + 100 + 0.85 * 130) / 3)

    def test_minority_interest_scales_the_cash_add_back(self):
        # parent owns 25% of the profit; D&A exceeds capex by 80 on a 100% basis
        h = history(ni=[25.0] * 10, ni_total=[100.0] * 10, da=[100.0] * 10)
        m = S.company_metrics(h)
        self.assertAlmostEqual(m["oe"], 25 + 0.25 * 80)

    def test_trailing_twelve_month_rows_are_ignored(self):
        h = history()
        ttm = h.iloc[[-1]].assign(cy=2026, fy_end=pd.Timestamp("2026-09-30"), ni=999.0)
        m = S.company_metrics(pd.concat([h, ttm]))
        self.assertEqual(m["fy_end"], pd.Timestamp("2025-12-31"))
        self.assertAlmostEqual(m["ni"], 100)

    def test_missing_capex_asset_heavy_gives_no_owner_earnings(self):
        m = S.company_metrics(history(capex=[NAN] * 10))   # D&A is 20% of income
        self.assertTrue(np.isnan(m["oe"]))

    def test_missing_capex_asset_light_assumes_capex_equals_da(self):
        m = S.company_metrics(history(capex=[NAN] * 10, da=[5.0] * 10))
        self.assertAlmostEqual(m["oe"], 100)
        self.assertEqual(m["data_notes"], "capex_assumed")

    def test_missing_da_is_taken_as_zero(self):
        m = S.company_metrics(history(da=[NAN] * 10))
        self.assertAlmostEqual(m["oe"], 80)       # 100 + 0 - 20: a lower bound
        self.assertEqual(m["data_notes"], "da_missing")

    def test_capex_gap_year_uses_reported_years(self):
        m = S.company_metrics(history(capex=[20.0] * 8 + [NAN, 40.0]))
        self.assertAlmostEqual(m["capex"], 30)    # 2023: 20, 2024: gap -> 30, 2025: 40

    def test_peak_margin_is_detected(self):
        pretax = [130.0] * 7 + [390.0] * 3      # margins triple in the last three years
        m = S.company_metrics(history(pretax=pretax))
        self.assertAlmostEqual(m["margin_ratio"], 0.5)   # 13% / 39%, clipped


class Classify(unittest.TestCase):
    ROW = {"cik": 1, "country": "United States", "industry": "Specialty Insurers"}

    def test_insurer_missed_by_sic_is_caught_by_premiums(self):
        m = S.company_metrics(history(premiums=[600.0] * 10))
        self.assertEqual(S.classify(self.ROW, m, {"sic": 6411}), "financial")

    def test_insurance_broker_is_valued(self):
        m = S.company_metrics(history())
        self.assertEqual(S.classify(self.ROW, m, {"sic": 6411}), "valued")

    def test_profit_without_owner_earnings_is_the_low_pe_trap(self):
        m = S.company_metrics(history(capex=[200.0] * 10))
        self.assertEqual(S.classify(self.ROW, m, {"sic": 4911}), "cash_burn")

    def test_unverifiable_income_is_not_valued(self):
        m = S.company_metrics(history(rev=[NAN] * 10))
        self.assertEqual(S.classify(self.ROW, m, {"sic": 6282}), "data_gap")


class Matching(unittest.TestCase):
    def test_name_key_survives_a_reorganisation(self):
        self.assertEqual(S._name_key("ExxonMobil Holdings Corporation Common Stock"),
                         S._name_key("EXXON MOBIL CORP"))
        self.assertNotEqual(S._name_key("Apple Inc. Common Stock"),
                            S._name_key("Applied Materials Inc. Common Stock"))

    def test_fiscal_year_month_is_inferred_from_history(self):
        h = history(fy_end=pd.to_datetime([f"{y}-06-30" for y in range(2016, 2026)]))
        m = S.company_metrics(h)
        self.assertEqual(m["fy_end"], pd.Timestamp("2025-06-30"))
        self.assertEqual(m["n_years"], 10)


class ScaleRepair(unittest.TestCase):
    def test_net_income_tagged_in_thousands_or_millions(self):
        from owner_earnings_screen.panel import repair_scale
        ni = pd.Series([2023000.0, 2593.0, 900.0, 5.0, NAN])
        total = pd.Series([2.023e9, 2.703e9, 1000.0, NAN, 50.0])
        pretax = pd.Series([2.6e9, 2.4e9, 1200.0, 7.0, 60.0])
        out, fixed = repair_scale(ni, [total, pretax])
        self.assertAlmostEqual(out[0], 2.023e9)
        self.assertAlmostEqual(out[1], 2.593e9)
        self.assertAlmostEqual(out[2], 900.0)      # already consistent
        self.assertAlmostEqual(out[3], 5.0)
        self.assertEqual(list(fixed), [True, True, False, False, False])


if __name__ == "__main__":
    unittest.main()
