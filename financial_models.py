# models/wacc.py
from dataclasses import dataclass

@dataclass
class WACCInputs:
    equity_weight: float       # e.g. 0.7
    debt_weight: float         # e.g. 0.3
    cost_of_equity: float      # from CAPM, e.g. 0.09
    cost_of_debt: float        # pre-tax, e.g. 0.05
    tax_rate: float            # corporate tax, e.g. 0.21

def calc_wacc(inputs: WACCInputs) -> float:
    """WACC = E/V * Re + D/V * Rd * (1 - Tc)"""
    return (
        inputs.equity_weight * inputs.cost_of_equity
        + inputs.debt_weight * inputs.cost_of_debt * (1 - inputs.tax_rate)
    )

def calc_cost_of_equity(risk_free: float, beta: float, market_premium: float) -> float:
    """CAPM: Re = Rf + β × (Rm - Rf)"""
    return risk_free + beta * market_premium


# models/fcf.py

def calc_fcf(operating_cashflow: float, capex: float) -> float:
    """Free Cash Flow = Operating Cash Flow - CapEx"""
    return operating_cashflow - abs(capex)

def calc_fcf_margin(fcf: float, revenue: float) -> float:
    """FCF Margin = FCF / Revenue"""
    if revenue == 0:
        return 0.0
    return fcf / revenue


# models/dcf.py
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class DCFScenario:
    name: str
    revenue_growth_rates: list[float]   # year-by-year, e.g. [0.20, 0.18, 0.15, 0.12, 0.10]
    fcf_margin: float                    # assumed stable FCF margin
    wacc: float
    terminal_growth: float               # Gordon Growth Model terminal rate
    exit_multiple: float | None = None   # EV/EBITDA for exit multiple method

@dataclass
class DCFResult:
    scenario: str
    pv_fcfs: list[float]
    terminal_value_gg: float             # Gordon Growth terminal value
    terminal_value_em: float | None      # Exit Multiple terminal value
    enterprise_value: float
    equity_value: float | None = None    # if net debt provided

def run_dcf(
    base_revenue: float,
    scenario: DCFScenario,
    net_debt: float = 0.0,
    ebitda: float | None = None,
) -> DCFResult:
    """
    Run a DCF with Gordon Growth and optionally Exit Multiple terminal value.
    Returns present values of projected FCFs and both terminal value methods.
    """
    revenues = []
    rev = base_revenue
    for g in scenario.revenue_growth_rates:
        rev *= (1 + g)
        revenues.append(rev)

    fcfs = [r * scenario.fcf_margin for r in revenues]
    n = len(fcfs)

    # Discount FCFs
    pv_fcfs = [fcf / (1 + scenario.wacc) ** (i + 1) for i, fcf in enumerate(fcfs)]

    # Terminal Value — Gordon Growth Model
    terminal_fcf = fcfs[-1] * (1 + scenario.terminal_growth)
    tv_gg = terminal_fcf / (scenario.wacc - scenario.terminal_growth)
    pv_tv_gg = tv_gg / (1 + scenario.wacc) ** n

    # Terminal Value — Exit Multiple (optional)
    pv_tv_em = None
    if scenario.exit_multiple and ebitda:
        terminal_ebitda = ebitda * (1 + scenario.revenue_growth_rates[-1]) ** n
        tv_em = terminal_ebitda * scenario.exit_multiple
        pv_tv_em = tv_em / (1 + scenario.wacc) ** n

    ev = sum(pv_fcfs) + pv_tv_gg
    equity = ev - net_debt

    return DCFResult(
        scenario=scenario.name,
        pv_fcfs=pv_fcfs,
        terminal_value_gg=pv_tv_gg,
        terminal_value_em=pv_tv_em,
        enterprise_value=ev,
        equity_value=equity,
    )


# models/sensitivity.py
import numpy as np

def sensitivity_matrix(
    base_revenue: float,
    fcf_margin: float,
    net_debt: float,
    wacc_range: list[float],
    tgr_range: list[float],
    projection_years: int = 5,
    growth_rate: float = 0.10,
) -> dict:
    """
    2D sensitivity: equity value vs (WACC × terminal growth rate).
    Returns a dict with axis labels and a 2D value matrix.
    """
    from .dcf import run_dcf, DCFScenario

    matrix = []
    for wacc in wacc_range:
        row = []
        for tgr in tgr_range:
            scenario = DCFScenario(
                name="sensitivity",
                revenue_growth_rates=[growth_rate] * projection_years,
                fcf_margin=fcf_margin,
                wacc=wacc,
                terminal_growth=tgr,
            )
            result = run_dcf(base_revenue, scenario, net_debt)
            row.append(round(result.equity_value / 1e9, 2))  # in billions
        matrix.append(row)

    return {
        "wacc_labels": [f"{w:.1%}" for w in wacc_range],
        "tgr_labels": [f"{t:.1%}" for t in tgr_range],
        "equity_value_bn": matrix,
    }
