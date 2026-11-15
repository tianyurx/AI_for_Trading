"""Parameters and tag lists for the owner-earnings screen."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"          # download cache, git-ignored
RESULTS_DIR = ROOT / "results"    # dated outputs, committed

# The SEC and Nasdaq both serve automated clients that identify themselves.
USER_AGENT = "owner-earnings-screen/0.1 (personal research script)"

# ---- valuation parameters -------------------------------------------------
UNIVERSE_SIZE = 2000
RISK_FREE = 0.05103          # 10-year Treasury yield (CBOE TNX 51.03, 2026-11-12 close)
RISK_FREE_ASOF = "2026-11-12"   # the Nasdaq listing carried that day's closing prices
GROWTH_ADJ = 0.03            # step 3: Buffett's 3-point pricing-power adjustment (1973)
MIN_CAP_RATE = 0.0381        # never capitalise below the 3.81% used for the Post
MARGIN_RATIO_CLIP = (0.5, 1.5)   # step 4: the Post's repair was 15%/10% = 1.5x
MIN_TAX = 0.15               # a year's net income is capped at 85% of pre-tax income
INSURER_PREMIUM_SHARE = 0.3  # premiums above this share of revenue: an insurer
AVG_YEARS = 3                # years averaged for "current" owner earnings
HIST_YEARS = 10              # look-back for quality and margin normalisation
MIN_HIST_YEARS = 5

FIRST_YEAR, LAST_YEAR = 2014, 2026

# ---- XBRL concepts (us-gaap), first tag with a value wins -----------------
DURATION_TAGS = {
    "ni_parent": ["NetIncomeLoss"],
    "ni_total": ["ProfitLoss"],          # including non-controlling interests
    "ni_common": ["NetIncomeLossAvailableToCommonStockholdersBasic"],
    "nci": ["NetIncomeLossAttributableToNoncontrollingInterest"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
           "DepreciationAmortizationAndAccretionNet",
           "CostOfGoodsAndServicesSoldDepreciationAndAmortization",
           "OtherDepreciationAndAmortization"],
    "dep": ["Depreciation"],
    "amort": ["AmortizationOfIntangibleAssets"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquireOtherProductiveAssets",
              "PaymentsForProceedsFromProductiveAssets",
              "PaymentsToAcquireOilAndGasPropertyAndEquipment",
              "PaymentsToAcquireOilAndGasProperty",
              "PaymentsToExploreAndDevelopOilAndGasProperties",
              "PaymentsForCapitalImprovements",
              "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
    "capsw": ["PaymentsToDevelopSoftware", "PaymentsForSoftware"],
    "capint": ["PaymentsToAcquireIntangibleAssets"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet", "SalesRevenueGoodsNet"],
    "pretax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "opinc": ["OperatingIncomeLoss"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "div": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "buyback": ["PaymentsForRepurchaseOfCommonStock"],
    "interest": ["InterestExpense", "InterestExpenseDebt",
                 "InterestExpenseNonoperating", "InterestPaidNet"],
    "premiums": ["PremiumsEarnedNet"],   # marks insurers the SIC code misses
}
# Filers often tag a sub-line under one of these names next to the true total
# under another, so the largest reported value is taken rather than the first.
LARGEST_OF = {"rev", "da", "capex"}
SHARE_TAGS = {"shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"]}
INSTANT_TAGS = {
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
}

# ---- SIC-based classification --------------------------------------------
def _r(a, b):
    return set(range(a, b + 1))

# balance-sheet financials: banks, lenders, broker-dealers, insurance carriers
SIC_FINANCIAL = _r(6000, 6199) | {6211, 6221} | _r(6300, 6399)
SIC_REIT = {6798}
SIC_FUND = {6770, 6726, 6722, 6189, 6795}
SIC_CYCLICAL = (_r(1000, 1499) | _r(1520, 1531) | _r(2600, 2631) | _r(2800, 2829)
                | _r(2860, 2879) | {2911} | _r(3310, 3399) | {3523, 3531, 3559, 3674}
                | _r(3711, 3716) | _r(4400, 4499) | {4512, 4513, 5051})
NASDAQ_CYCLICAL_SECTORS = {"Energy", "Basic Materials"}
