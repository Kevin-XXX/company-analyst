# data/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class FinancialData:
    ticker: str
    income_statement: dict
    balance_sheet: dict
    cash_flow: dict
    key_ratios: dict
    source: str

class DataProvider(ABC):
    """Abstract base — all fetchers implement this interface."""

    @abstractmethod
    def get_financials(self, ticker: str) -> FinancialData:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is reachable."""
        pass


# data/yfinance_fetcher.py
import yfinance as yf
from .base import DataProvider, FinancialData

class YFinanceFetcher(DataProvider):

    def is_available(self) -> bool:
        try:
            import yfinance
            return True
        except ImportError:
            return False

    def get_financials(self, ticker: str) -> FinancialData:
        stock = yf.Ticker(ticker)
        info = stock.info

        income = {
            "revenue": info.get("totalRevenue"),
            "gross_profit": info.get("grossProfits"),
            "net_income": info.get("netIncomeToCommon"),
            "ebitda": info.get("ebitda"),
            "gross_margin": info.get("grossMargins"),
            "operating_margin": info.get("operatingMargins"),
        }

        balance = {
            "total_assets": info.get("totalAssets"),
            "total_debt": info.get("totalDebt"),
            "total_equity": info.get("bookValue"),
            "cash": info.get("totalCash"),
            "debt_to_equity": info.get("debtToEquity"),
        }

        cashflow = {
            "operating_cashflow": info.get("operatingCashflow"),
            "capital_expenditure": info.get("capitalExpenditures"),
            "free_cashflow": info.get("freeCashflow"),
        }

        ratios = {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "roic": None,  # not directly in yfinance info
            "current_ratio": info.get("currentRatio"),
            "interest_coverage": None,
        }

        return FinancialData(
            ticker=ticker,
            income_statement=income,
            balance_sheet=balance,
            cash_flow=cashflow,
            key_ratios=ratios,
            source="yfinance"
        )


# data/fmp_fetcher.py
import os
import requests
from .base import DataProvider, FinancialData

FMP_BASE = "https://financialmodelingprep.com/api/v3"

class FMPFetcher(DataProvider):

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_financials(self, ticker: str) -> FinancialData:
        params = {"apikey": self.api_key}

        income_raw = requests.get(f"{FMP_BASE}/income-statement/{ticker}", params={**params, "limit": 1}).json()
        balance_raw = requests.get(f"{FMP_BASE}/balance-sheet-statement/{ticker}", params={**params, "limit": 1}).json()
        cashflow_raw = requests.get(f"{FMP_BASE}/cash-flow-statement/{ticker}", params={**params, "limit": 1}).json()
        ratios_raw = requests.get(f"{FMP_BASE}/ratios-ttm/{ticker}", params=params).json()

        i = income_raw[0] if income_raw else {}
        b = balance_raw[0] if balance_raw else {}
        c = cashflow_raw[0] if cashflow_raw else {}
        r = ratios_raw[0] if ratios_raw else {}

        income = {
            "revenue": i.get("revenue"),
            "gross_profit": i.get("grossProfit"),
            "net_income": i.get("netIncome"),
            "ebitda": i.get("ebitda"),
            "gross_margin": i.get("grossProfitRatio"),
            "operating_margin": i.get("operatingIncomeRatio"),
        }

        balance = {
            "total_assets": b.get("totalAssets"),
            "total_debt": b.get("totalDebt"),
            "total_equity": b.get("totalStockholdersEquity"),
            "cash": b.get("cashAndCashEquivalents"),
            "debt_to_equity": r.get("debtEquityRatioTTM"),
        }

        cashflow = {
            "operating_cashflow": c.get("operatingCashFlow"),
            "capital_expenditure": c.get("capitalExpenditure"),
            "free_cashflow": c.get("freeCashFlow"),
        }

        ratios = {
            "pe_ratio": r.get("peRatioTTM"),
            "forward_pe": None,
            "peg_ratio": r.get("pegRatioTTM"),
            "price_to_book": r.get("priceToBookRatioTTM"),
            "roe": r.get("returnOnEquityTTM"),
            "roic": r.get("returnOnCapitalEmployedTTM"),
            "current_ratio": r.get("currentRatioTTM"),
            "interest_coverage": r.get("interestCoverageTTM"),
        }

        return FinancialData(
            ticker=ticker,
            income_statement=income,
            balance_sheet=balance,
            cash_flow=cashflow,
            key_ratios=ratios,
            source="fmp"
        )


# data/fallback.py
from .base import DataProvider, FinancialData
from .yfinance_fetcher import YFinanceFetcher
from .fmp_fetcher import FMPFetcher

class FallbackProvider:
    """Try providers in order, fall back automatically."""

    def __init__(self):
        self.providers: list[DataProvider] = [
            FMPFetcher(),       # preferred: more complete
            YFinanceFetcher(),  # fallback: always free
        ]

    def get_financials(self, ticker: str) -> FinancialData:
        for provider in self.providers:
            if provider.is_available():
                try:
                    return provider.get_financials(ticker)
                except Exception as e:
                    print(f"[fallback] {provider.__class__.__name__} failed: {e}")
        raise RuntimeError(f"All data providers failed for {ticker}")
