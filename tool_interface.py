# tools/schemas.py
# OpenAI / Claude compatible function schemas

TOOL_SCHEMAS = [
    {
        "name": "fetch_financials",
        "description": "Fetch structured financial data for a company including income statement, balance sheet, cash flow, and key ratios. Use this before any valuation or analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. AAPL, NVDA, 0700.HK"
                },
                "period": {
                    "type": "string",
                    "enum": ["annual", "quarterly"],
                    "description": "Reporting period. Default: annual.",
                    "default": "annual"
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "run_dcf",
        "description": "Run a Discounted Cash Flow model with multiple scenarios and sensitivity analysis. Call this after fetch_financials to produce a valuation range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "base_revenue": {
                    "type": "number",
                    "description": "Most recent annual revenue in USD"
                },
                "fcf_margin": {
                    "type": "number",
                    "description": "Assumed FCF margin as a decimal, e.g. 0.25 for 25%"
                },
                "wacc": {
                    "type": "number",
                    "description": "Weighted average cost of capital, e.g. 0.10"
                },
                "scenarios": {
                    "type": "array",
                    "description": "List of scenario names to model: bull, base, bear",
                    "items": {"type": "string", "enum": ["bull", "base", "bear"]},
                    "default": ["bull", "base", "bear"]
                },
                "net_debt": {
                    "type": "number",
                    "description": "Total debt minus cash, in USD. Use negative for net cash position.",
                    "default": 0
                }
            },
            "required": ["ticker", "base_revenue", "fcf_margin", "wacc"]
        }
    },
    {
        "name": "get_sentiment",
        "description": "Fetch current market sentiment indicators including Fear & Greed Index, analyst consensus, and macro policy context for the company's market.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "market": {
                    "type": "string",
                    "enum": ["US", "HK", "CN", "EU", "AU"],
                    "description": "Primary market for policy/central bank context.",
                    "default": "US"
                }
            },
            "required": ["ticker"]
        }
    }
]


# tools/fetch_financials.py
from data.fallback import FallbackProvider

def fetch_financials(ticker: str, period: str = "annual") -> dict:
    provider = FallbackProvider()
    data = provider.get_financials(ticker)
    return {
        "ticker": data.ticker,
        "source": data.source,
        "income_statement": data.income_statement,
        "balance_sheet": data.balance_sheet,
        "cash_flow": data.cash_flow,
        "key_ratios": data.key_ratios,
    }


# tools/run_dcf.py
from models.dcf import run_dcf as _run_dcf, DCFScenario
from models.sensitivity import sensitivity_matrix

SCENARIO_CONFIGS = {
    "bull": {"growth_rates": [0.25, 0.22, 0.20, 0.18, 0.15], "terminal_growth": 0.04},
    "base": {"growth_rates": [0.15, 0.13, 0.12, 0.10, 0.08], "terminal_growth": 0.03},
    "bear": {"growth_rates": [0.08, 0.07, 0.06, 0.05, 0.04], "terminal_growth": 0.02},
}

def run_dcf(ticker: str, base_revenue: float, fcf_margin: float,
            wacc: float, scenarios: list = ["bull", "base", "bear"],
            net_debt: float = 0.0) -> dict:

    results = {}
    for name in scenarios:
        cfg = SCENARIO_CONFIGS[name]
        scenario = DCFScenario(
            name=name,
            revenue_growth_rates=cfg["growth_rates"],
            fcf_margin=fcf_margin,
            wacc=wacc,
            terminal_growth=cfg["terminal_growth"],
        )
        r = _run_dcf(base_revenue, scenario, net_debt)
        results[name] = {
            "enterprise_value_bn": round(r.enterprise_value / 1e9, 1),
            "equity_value_bn": round(r.equity_value / 1e9, 1),
            "terminal_value_bn": round(r.terminal_value_gg / 1e9, 1),
        }

    sensitivity = sensitivity_matrix(
        base_revenue=base_revenue,
        fcf_margin=fcf_margin,
        net_debt=net_debt,
        wacc_range=[0.08, 0.09, 0.10, 0.11, 0.12],
        tgr_range=[0.02, 0.025, 0.03, 0.035, 0.04],
    )

    return {"ticker": ticker, "scenarios": results, "sensitivity": sensitivity}
