"""
analyze.py — Company Analyst Main Entry Point
Usage:
    python analyze.py AAPL
    python analyze.py NVDA --lang zh
    python analyze.py NOK --no-browser

Flow:
    1. Fetch live data from yfinance
    2. Run valuation engine (PE percentile + dynamic DCF + comps)
    3. Build qualitative context via web search (if available)
    4. Convert to report data dict
    5. Generate HTML report
    6. Open in browser
"""

import sys
import os
import argparse
import datetime
import webbrowser
import json

# ── Path setup (works whether run from repo root or any subdirectory) ──
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Fetch live financial data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_data(ticker: str) -> dict:
    """Pull everything we need from yfinance in one shot."""
    import yfinance as yf

    print(f"  [1/4] Fetching live data for {ticker}...")
    stock = yf.Ticker(ticker)
    info  = stock.info

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        raise ValueError(f"No data found for ticker '{ticker}'. Check the symbol.")

    # Current price — prefer real-time, fall back to previous close
    price = (info.get("currentPrice")
             or info.get("regularMarketPrice")
             or info.get("previousClose")
             or 0)

    # Income statement
    revenue      = info.get("totalRevenue") or 0
    gross_profit = info.get("grossProfits") or 0
    net_income   = info.get("netIncomeToCommon") or 0
    ebitda       = info.get("ebitda") or 0
    gross_margin = info.get("grossMargins") or (gross_profit / revenue if revenue else 0)
    op_margin    = info.get("operatingMargins") or 0

    # Balance sheet
    total_debt   = info.get("totalDebt") or 0
    total_cash   = info.get("totalCash") or 0
    net_cash     = total_cash - total_debt
    book_value   = info.get("bookValue") or 0
    shares       = info.get("sharesOutstanding") or 1

    # Cash flow
    op_cf        = info.get("operatingCashflow") or 0
    capex        = info.get("capitalExpenditures") or 0
    fcf          = info.get("freeCashflow") or (op_cf - abs(capex))
    fcf_margin   = fcf / revenue if revenue else 0

    # Ratios
    pe           = info.get("trailingPE")
    fwd_pe       = info.get("forwardPE")
    peg          = info.get("pegRatio")
    roe          = info.get("returnOnEquity") or 0
    pb           = info.get("priceToBook")
    ps           = info.get("priceToSalesTrailing12Months")
    beta         = info.get("beta") or 1.0
    div_yield    = info.get("dividendYield") or 0

    # Company meta
    name         = info.get("longName") or info.get("shortName") or ticker
    sector       = info.get("sector") or "Technology"
    industry     = info.get("industry") or ""
    country      = info.get("country") or "US"
    exchange     = info.get("exchange") or "NYSE"
    mktcap       = info.get("marketCap") or (price * shares)
    week52_high  = info.get("fiftyTwoWeekHigh") or price
    week52_low   = info.get("fiftyTwoWeekLow") or price
    analyst_target = info.get("targetMeanPrice")
    analyst_count  = info.get("numberOfAnalystOpinions") or 0
    recommendation = info.get("recommendationKey") or "hold"
    eps_ttm      = info.get("trailingEps") or 0
    eps_fwd      = info.get("forwardEps") or 0

    # Interest coverage (approximate: EBITDA / interest expense)
    interest_exp  = info.get("interestExpense") or None
    interest_cov  = round(ebitda / abs(interest_exp), 1) if interest_exp and interest_exp != 0 else None

    return {
        # Identity
        "ticker":        ticker.upper(),
        "company_name":  name,
        "sector":        sector,
        "industry":      industry,
        "country":       country,
        "exchange":      exchange,

        # Price
        "current_price": round(price, 2),
        "week52_high":   round(week52_high, 2),
        "week52_low":    round(week52_low, 2),
        "mktcap_bn":     round(mktcap / 1e9, 1),

        # Financials
        "revenue":       revenue,
        "gross_profit":  gross_profit,
        "net_income":    net_income,
        "ebitda":        ebitda,
        "gross_margin":  gross_margin,
        "op_margin":     op_margin,
        "fcf":           fcf,
        "fcf_margin":    fcf_margin,
        "total_debt":    total_debt,
        "total_cash":    total_cash,
        "net_cash":      net_cash,
        "book_value":    book_value,
        "shares":        shares,
        "op_cf":         op_cf,

        # Ratios
        "pe":            pe,
        "fwd_pe":        fwd_pe,
        "peg":           peg,
        "roe":           roe,
        "pb":            pb,
        "ps":            ps,
        "beta":          beta,
        "div_yield":     div_yield,
        "eps_ttm":       eps_ttm,
        "eps_fwd":       eps_fwd,
        "interest_cov":  interest_cov,

        # Analyst
        "analyst_target":  analyst_target,
        "analyst_count":   analyst_count,
        "recommendation":  recommendation,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Run valuation engine
# ─────────────────────────────────────────────────────────────────────────────

def run_valuation(ticker: str, live: dict, rf_rate: float = 0.043) -> dict:
    """Run PE percentile + dynamic DCF + comps, return combined result dict."""
    from valuation_engine import (
        pe_percentile, dynamic_dcf, comps_valuation,
        FullValuation, PEPercentileResult, DynamicDCFResult, CompsResult,
    )
    import numpy as np

    print(f"  [2/4] Running valuation engine...")

    # PE percentile
    try:
        pe_res = pe_percentile(ticker)
        print(f"        PE percentile: {pe_res.percentile}th ({pe_res.label})")
    except Exception as e:
        print(f"        PE percentile failed ({e}), using fallback")
        current_pe = live.get("pe") or 0
        pe_res = PEPercentileResult(
            current_pe=current_pe, pe_5yr_median=0, pe_5yr_min=0, pe_5yr_max=0,
            percentile=50, premium_to_median_pct=0,
            label="N/A", color="#888",
            plain_text="Historical PE percentile data unavailable.",
        )

    # Dynamic DCF
    try:
        dcf_res = dynamic_dcf(ticker, rf_rate=rf_rate)
        for s in dcf_res.scenarios:
            print(f"        DCF {s.name}: ${s.price_per_share:.2f}/sh")
    except Exception as e:
        print(f"        DCF failed ({e}), using simplified DCF")
        dcf_res = _simplified_dcf(live, rf_rate)

    # Comps
    try:
        comps_res = comps_valuation(ticker)
        print(f"        Comps blended FV: ${comps_res.blended_fair_value:.2f}")
    except Exception as e:
        print(f"        Comps failed ({e}), skipping")
        comps_res = None

    # Blended fair value
    dcf_base  = next((s.price_per_share for s in dcf_res.scenarios if s.name == "Base"), 0)
    dcf_bear  = next((s.price_per_share for s in dcf_res.scenarios if s.name == "Bear"), 0)
    comps_fv  = comps_res.blended_fair_value if comps_res and comps_res.blended_fair_value > 0 else 0

    if comps_fv > 0:
        blended = round(0.50 * dcf_base + 0.30 * comps_fv + 0.20 * dcf_bear, 2)
        method  = "50% DCF Base + 30% Peer Comps + 20% DCF Bear"
    else:
        blended = round(0.70 * dcf_base + 0.30 * dcf_bear, 2)
        method  = "70% DCF Base + 30% DCF Bear"

    if comps_res is None:
        comps_res = _empty_comps(ticker)

    return {
        "pe_res":   pe_res,
        "dcf_res":  dcf_res,
        "comps_res": comps_res,
        "blended_fv": blended,
        "blend_method": method,
    }


def _simplified_dcf(live: dict, rf_rate: float) -> object:
    """Fallback: simple 3-scenario DCF when valuation_engine fails."""
    from valuation_engine import DynamicDCFResult, DCFScenario
    import numpy as np

    revenue    = live["revenue"]
    fcf_margin = max(0.05, min(0.50, live["fcf_margin"]))
    beta       = live["beta"]
    net_debt   = live["total_debt"] - live["total_cash"]
    shares     = live["shares"]
    wacc       = max(0.07, min(0.20, rf_rate + beta * 0.05))

    def _dcf_single(rev, fcm, growth_rates, w, tg):
        r = rev
        pvs = []
        for i, g in enumerate(growth_rates):
            r *= (1 + g)
            pvs.append(r * fcm / (1 + w) ** (i + 1))
        tv  = r * fcm * (1 + tg) / max(w - tg, 0.01)
        pv_tv = tv / (1 + w) ** len(growth_rates)
        eq = sum(pvs) + pv_tv - net_debt
        return round(eq / 1e9, 1), round(eq / shares, 2)

    scenarios = []
    for name, rates, tg, wf in [
        ("Bull", [0.20,0.18,0.15,0.12,0.10], 0.04, 0.95),
        ("Base", [0.12,0.10,0.08,0.07,0.06], 0.03, 1.00),
        ("Bear", [0.05,0.04,0.04,0.03,0.03], 0.02, 1.05),
    ]:
        ev_bn, px = _dcf_single(revenue, fcf_margin, rates, wacc * wf, tg)
        scenarios.append(DCFScenario(
            name=name, revenue_growth_rates=rates, fcf_margin=fcf_margin,
            wacc=round(wacc * wf, 3), terminal_growth=tg,
            equity_value_bn=ev_bn, price_per_share=px,
        ))

    wacc_range = [round(wacc - 0.02 + i * 0.01, 2) for i in range(5)]
    tgr_range  = [0.02, 0.025, 0.03, 0.035, 0.04]
    matrix = []
    for w in wacc_range:
        row = []
        for tg in tgr_range:
            ev_bn, _ = _dcf_single(revenue, fcf_margin, [0.12,0.10,0.08,0.07,0.06], w, tg)
            row.append(ev_bn)
        matrix.append(row)

    return DynamicDCFResult(
        scenarios=scenarios,
        base_growth_source="revenue trend (fallback)",
        consensus_growth_yr1=12.0,
        wacc_used=wacc,
        wacc_basis=f"CAPM fallback: β={beta:.2f} WACC={wacc*100:.1f}%",
        sensitivity={
            "wacc_labels": [f"{int(w*100)}%" for w in wacc_range],
            "tgr_labels":  [f"{tg*100:.1f}%" for tg in tgr_range],
            "equity_value_bn": matrix,
        },
        net_debt=net_debt,
    )


def _empty_comps(ticker: str):
    from valuation_engine import CompsResult
    return CompsResult(
        subject_ticker=ticker, subject_metrics={}, peers=[],
        peer_medians={}, premium_discount={}, implied_price_range={},
        blended_fair_value=0.0, summary="Peer comparison data unavailable.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Build report data dict
# ─────────────────────────────────────────────────────────────────────────────

def build_report_data(ticker: str, live: dict, val: dict, lang: str = "en") -> dict:
    """Combine live data + valuation results into the report_generator data dict."""
    print(f"  [3/4] Building report data...")

    pe_res   = val["pe_res"]
    dcf_res  = val["dcf_res"]
    comps_res = val["comps_res"]
    blended  = val["blended_fv"]
    method   = val["blend_method"]

    price       = live["current_price"]
    base_px     = next((s.price_per_share for s in dcf_res.scenarios if s.name=="Base"), 0)
    bull_px     = next((s.price_per_share for s in dcf_res.scenarios if s.name=="Bull"), 0)
    bear_px     = next((s.price_per_share for s in dcf_res.scenarios if s.name=="Bear"), 0)

    gap_vs_blended = round((price - blended) / blended * 100, 0) if blended > 0 else 0
    gap_str = f"+{int(gap_vs_blended)}%" if gap_vs_blended >= 0 else f"{int(gap_vs_blended)}%"
    gap_col = "above" if gap_vs_blended > 0 else "below"

    # ── Format financial table ──
    def _fmt(val, scale=1, prefix="$", suffix="", decimals=1):
        if val is None: return "N/A"
        v = val / scale
        return f"{prefix}{v:.{decimals}f}{suffix}"

    def _pct(val):
        if val is None: return "N/A"
        return f"{val*100:.1f}%"

    def _sig(val, thresholds, labels=("🟢","🟡","🔴"), notes=("","","")):
        """Map a value to a signal based on thresholds (higher is better by default)."""
        if val is None: return "🟡 N/A"
        for i, t in enumerate(thresholds):
            if val >= t:
                return f"{labels[i]} {notes[i]}" if notes[i] else labels[i]
        return f"{labels[-1]} {notes[-1]}" if notes[-1] else labels[-1]

    revenue_b = live["revenue"] / 1e9
    ni_b      = live["net_income"] / 1e9
    fcf_b     = live["fcf"] / 1e9
    net_cash_b = live["net_cash"] / 1e9

    financials = {
        "Free Cash Flow":    {
            "value": f"${fcf_b:.1f}B",
            "signal": _sig(live["fcf_margin"], [0.15, 0.05, 0],
                          notes=["Excellent (>15%)","Positive","Negative — cash burn"]),
        },
        "ROE":               {
            "value": _pct(live["roe"]),
            "signal": _sig(live["roe"], [0.20, 0.10, 0],
                          notes=["Strong (>20%)","Adequate","Below threshold"]),
        },
        "Gross Margin":      {
            "value": _pct(live["gross_margin"]),
            "signal": _sig(live["gross_margin"], [0.40, 0.20, 0],
                          notes=["High (>40%)","Mid range","Low (<20%)"]),
        },
        "Net Cash Position": {
            "value": f"${net_cash_b:+.1f}B",
            "signal": "🟢 Net cash" if live["net_cash"] > 0 else "🔴 Net debt",
        },
        "Revenue (TTM)":     {
            "value": f"${revenue_b:.1f}B",
            "signal": "🟢 See growth trend",
        },
        "Net Income":        {
            "value": f"${ni_b:.1f}B",
            "signal": "🟢 Profitable" if ni_b > 0 else "🔴 Loss-making",
        },
        "FCF Margin":        {
            "value": _pct(live["fcf_margin"]),
            "signal": _sig(live["fcf_margin"], [0.15, 0.05, 0],
                          notes=[">15% excellent","Positive","Negative"]),
        },
    }

    if live["pe"]:
        financials["PE Ratio (TTM)"] = {
            "value": f"{live['pe']:.1f}x",
            "signal": _sig(1/live["pe"] if live["pe"] else 0,
                          [1/15, 1/30, 0],
                          notes=["Below 15x","15-30x","Above 30x — elevated"]),
        }
    if live["interest_cov"]:
        financials["Interest Coverage"] = {
            "value": f"{live['interest_cov']:.1f}x",
            "signal": _sig(live["interest_cov"], [5, 3, 0],
                          notes=[">5x safe",">3x manageable","<3x risky"]),
        }

    # ── DCF scenarios ──
    dcf_scenarios = [
        {"scenario": s.name, "equity_value_bn": s.equity_value_bn, "price_per_share": s.price_per_share}
        for s in dcf_res.scenarios
    ]

    # ── Margins for donut charts ──
    margins = {
        "gross_margin": round(live["gross_margin"] * 100, 1),
        "fcf_margin":   round(live["fcf_margin"] * 100, 1),
        "net_margin":   round((live["net_income"] / live["revenue"] * 100) if live["revenue"] else 0, 1),
    }

    # ── Scorecard — auto-generated from data ──
    scorecard = _build_scorecard(live, pe_res, gap_vs_blended)

    # ── Market temp ──
    pe_vs_hist_label = (
        f"{live['pe']:.1f}x vs {pe_res.pe_5yr_median:.1f}x 5yr median"
        if live["pe"] and pe_res.pe_5yr_median
        else "PE data unavailable"
    )
    beta_level = "hot" if live["beta"] > 1.5 else ("warm" if live["beta"] > 1.0 else "normal")

    analyst_label = None
    if live["analyst_target"] and live["analyst_count"] > 0:
        updown = round((live["analyst_target"] - price) / price * 100, 0)
        sign   = "+" if updown >= 0 else ""
        rec    = live["recommendation"].replace("_", " ").title()
        analyst_label = f"{rec} — target ${live['analyst_target']:.2f} ({sign}{int(updown)}% vs current)"

    pe_pct_level = "hot" if pe_res.percentile > 85 else ("warm" if pe_res.percentile > 60 else "normal")

    market_temp = {
        "fear_greed": {"score": "See market.data", "level": "warm", "pct": 60},
        "pe_vs_history": {
            "value": pe_vs_hist_label,
            "level": pe_pct_level,
            "pct": pe_res.percentile,
        },
        "analyst_expectations": {
            "value": analyst_label,
            "level": "warm" if analyst_label else None,
            "pct": 60,
        },
        "beta": {
            "value": f"{live['beta']:.2f}",
            "level": beta_level,
            "pct": min(int(live["beta"] * 50), 100),
        },
    }

    # ── Price anchor ──
    price_anchor = {
        "current_price": price,
        "fair_value":    round(blended, 2),
        "dcf_base":      round(base_px, 2),
        "comps_fv":      round(comps_res.blended_fair_value, 2),
        "gap_pct":       gap_str,
        "gap_label": (
            f"At ${price}, the stock trades {gap_str} {gap_col} the blended fair value "
            f"(${blended:.0f}, computed as {method}). "
            f"This is a reference point, not a prediction."
        ),
    }

    # ── Historical drawdown estimate (rough) ──
    pct_from_52wk_high = round((price - live["week52_high"]) / live["week52_high"] * 100, 0)
    hist_drawdowns = {
        "max":  f"{int(pct_from_52wk_high)}% from 52-wk high (${live['week52_high']})",
        "avg":  "Data unavailable",
    }

    # ── Company profile — auto-built from yfinance + structured parsing ──
    company_profile = _build_company_profile(ticker, live)

    # ── Executive Summary — generated from live data + profile ──
    executive_summary = _build_executive_summary(ticker, live, company_profile, blended, gap_str, pe_res)

    # ── Yellow Decision Card — 3-Step Tactical Structure (data-driven scaffolds) ──

    # Step 1 — Valuation Anchor & Psychological State (1 paragraph, no formulas)
    gap_num = float(gap_str.replace("%","").replace("+",""))
    if gap_num > 50:
        valuation_anchor = (
            f"At ${price}, the market is pricing in flawless execution well beyond the Bull Case. "
            f"Any operational slip, guidance miss, or sentiment rotation will hit the stock disproportionately."
        )
    elif gap_num > 20:
        valuation_anchor = (
            f"At ${price}, the stock carries a growth premium that leaves minimal room for error. "
            f"The market has already baked in an optimistic trajectory — confirmation risk is high."
        )
    elif gap_num > -20:
        valuation_anchor = (
            f"At ${price}, valuation is broadly in line with the modelled fair-value range. "
            f"Upside and downside are roughly symmetrical from here — the narrative, not the multiple, will drive the next move."
        )
    else:
        valuation_anchor = (
            f"At ${price}, the market may be underpricing the underlying fundamentals. "
            f"Verify that the bear-case fears are real and not extrapolated — a margin of safety could be forming."
        )

    # Step 2 — Key Tactical Risk (1 concrete fundamental threat, sector-aware)
    sector_risk_map = {
        "Technology":        "Platform transition risk: a shift in architecture or customer stack could erode the installed base faster than the DCF assumes.",
        "Healthcare":        "Reimbursement or regulatory pivot: a single FDA decision or pricing reform can re-rate the revenue trajectory overnight.",
        "Financial Services":"Net-interest margin compression or credit-cycle deterioration that hits earnings before the balance sheet shows stress.",
        "Consumer Cyclical":"Demand elasticity: a consumer-spending pullback exposes operating leverage and inventory write-downs.",
        "Consumer Defensive":"Volume vs price trade-off: private-label share gains or input-cost inflation squeezes the margin structure.",
        "Industrials":       "Order-cycle freeze: a delay in capex decisions from key customers extends the backlog conversion timeline.",
        "Energy":            "Commodity price collapse or energy-transition policy shock that strands high-cost production assets.",
        "Communication Services":"Subscriber saturation and ARPU stagnation combined with content-cost inflation.",
        "Real Estate":       "Cap-rate expansion driven by higher-for-longer rates, eroding property NAVs.",
        "Basic Materials":   "Inventory destocking across the manufacturing chain triggering a violent price correction.",
        "Utilities":         "Rate-base growth caps and rising cost of capital that compresses allowed ROE.",
    }
    key_risk = sector_risk_map.get(live["sector"], "Execution or competitive risk that undermines the assumptions baked into the forward growth rate.")

    # Step 3 — Dynamic Triggers (3 clean, quantitative invalidation triggers)
    triggers = []
    # Price trigger
    if gap_vs_blended > 30:
        pt = round(blended * 1.1, 0)
        triggers.append(f"Price: A pullback to ~${pt:.0f} (near blended fair value) would restore a structural margin of safety.")
    elif gap_vs_blended < -20:
        triggers.append(f"Price: A further drop of 15% from here would push the stock into deep-value territory — confirm fundamentals first.")
    else:
        triggers.append(f"Price: A break above ${live['week52_high']:.0f} on volume would invalidate the neutral-range thesis.")
    # Fundamental trigger
    if live["analyst_target"]:
        triggers.append(f"Fundamental: Two consecutive quarters missing revenue consensus — the ${live['analyst_target']:.2f} analyst target would likely be revised down.")
    else:
        triggers.append("Fundamental: Two consecutive quarters of revenue deceleration below the DCF base-case growth rate.")
    # Macro trigger
    triggers.append("Macro: A sector-wide multiple compression (central bank policy shift or risk-off rotation) that drags the peer-group P/E down by 20%+.")

    # ── WACC and DCF metadata ──
    dcf_meta = {
        "base_growth_source":   dcf_res.base_growth_source,
        "consensus_growth_yr1": dcf_res.consensus_growth_yr1,
        "wacc":                 dcf_res.wacc_used,
        "wacc_basis":           dcf_res.wacc_basis,
    }

    # ── Bull / Bear case dot points (data-driven; AI enrichment may refine with company specifics) ──
    _sector = live.get("sector") or "the sector"
    _cname  = live.get("company_name") or ticker
    bull_case = {
        "target_price": bull_px,
        "points": [
            f"Reaching the ${bull_px:.0f} Bull target requires {_cname} to sustain its upper-bound growth path and defend pricing power against {_sector} competition.",
            f"Margin expansion or a favourable product mix shift that lifts free-cash-flow generation above the base-case assumption.",
        ],
    }
    bear_case = {
        "target_price": bear_px,
        "points": [
            f"A slide toward the ${bear_px:.0f} Bear floor would follow a structural demand or competitive shock in {_sector} that erodes the installed revenue base.",
            f"Growth deceleration below the DCF base-case rate, compressing the valuation multiple as the market re-rates the forward outlook.",
        ],
    }

    date_str = datetime.date.today().strftime("%Y-%m-%d")

    return {
        # Identity
        "ticker":          ticker,
        "company_name":    live["company_name"],
        "date":            date_str,
        "current_price":   price,

        # Valuation metadata
        "valuation_percentile": pe_res.percentile,
        "pe_detail":       {
            "current":           pe_res.current_pe,
            "median_5yr":        pe_res.pe_5yr_median,
            "min_5yr":           pe_res.pe_5yr_min,
            "max_5yr":           pe_res.pe_5yr_max,
            "premium_to_median": pe_res.premium_to_median_pct,
            "label":             pe_res.label,
            "color":             pe_res.color,
            "plain_text":        pe_res.plain_text,
        },
        "dcf_meta":        dcf_meta,
        "combined_fair_value": blended,
        "blend_method":    method,
        "comps_summary":   comps_res.summary,

        # Report sections
        "company_profile": company_profile,
        "executive_summary": executive_summary,
        "financials":      financials,
        "financials_appendix": financials,   # duplicated for bottom-details relocation
        "margins":         margins,
        "dcf_scenarios":   dcf_scenarios,
        "sensitivity":     dcf_res.sensitivity,
        "scorecard":       scorecard,
        "market_temp":     market_temp,
        "price_anchor":    price_anchor,
        "historical_drawdowns": hist_drawdowns,

        # Decision card (Bull / Bear dual-core + 3-Step Tactical)
        "bull_case":       bull_case,
        "bear_case":       bear_case,
        "valuation_anchor": valuation_anchor,
        "key_risk":        key_risk,
        "condition_triggers": triggers,
        "risk_score":      _risk_score(scorecard),
        "dcf_limitation":  f"DCF uses {dcf_res.base_growth_source} as the base growth rate ({dcf_res.consensus_growth_yr1}% yr1). WACC calibrated via CAPM: {dcf_res.wacc_basis}. Terminal value uses Gordon Growth Model.",

        # Legacy facts (retained for backward compatibility)
        "fact_business":   f"Core business: {live['industry']} | Gross margin {live['gross_margin']*100:.1f}% | ROE {live['roe']*100:.1f}%",
        "fact_valuation":  f"PE {live['pe']:.1f}x at {pe_res.percentile}th 5yr percentile (median: {pe_res.pe_5yr_median:.1f}x). Blended fair value ${blended:.0f} vs current ${price}." if live["pe"] else f"Blended fair value ${blended:.0f} vs current ${price}.",
        "fact_risk":       "Key risks: see Risk Register in signal scorecard. Top risk identified by model: " + _top_risk(live, scorecard),

        # Analyst explanation (placeholders — enriched by Claude in SKILL.md flow)
        "analyst_conclusion": {
            "why_this_verdict":  f"The blended fair value of ${blended:.0f} is derived from {method}; the current PE sits at the {pe_res.percentile}th percentile of its five-year range, which frames how much of the outlook is already reflected in the price.",
            "model_blind_spots": "Qualitative factors such as brand value, strategic optionality, and platform effects are not captured by a DCF, and terminal value is highly sensitive to the long-run growth assumption.",
        },
    }


def _build_scorecard(live: dict, pe_res, gap_pct: float) -> dict:
    """Auto-generate scorecard signals from live data."""

    # Financial health
    if live["gross_margin"] > 0.40 and live["fcf"] > 0 and live["net_cash"] > 0:
        fh_sig = "green"
    elif live["net_income"] < 0 or live["fcf"] < 0:
        fh_sig = "red"
    else:
        fh_sig = "yellow"

    # Earnings quality: FCF vs net income
    ni = live["net_income"]
    fcf = live["fcf"]
    if ni > 0 and fcf > 0:
        ratio = fcf / ni
        eq_sig = "green" if ratio > 0.8 else ("yellow" if ratio > 0.4 else "red")
    elif fcf > 0:
        eq_sig = "yellow"
    else:
        eq_sig = "red"

    # Moat: proxy via gross margin and ROE
    if live["gross_margin"] > 0.40 and (live["roe"] or 0) > 0.15:
        moat_sig = "green"
    elif live["gross_margin"] > 0.20 and (live["roe"] or 0) > 0.05:
        moat_sig = "yellow"
    else:
        moat_sig = "red"

    # Valuation
    if gap_pct > 50:
        val_sig = "red"
    elif gap_pct > 10:
        val_sig = "yellow"
    else:
        val_sig = "green"

    # Sentiment: PE percentile
    if pe_res.percentile > 80:
        sent_sig = "red"
    elif pe_res.percentile > 50:
        sent_sig = "yellow"
    else:
        sent_sig = "green"

    # Policy risk: proxy via beta and country
    beta = live["beta"]
    if beta > 1.5:
        pol_sig = "yellow"
    else:
        pol_sig = "green"

    def _note(sig, green_txt, yellow_txt, red_txt):
        return {"green": green_txt, "yellow": yellow_txt, "red": red_txt}[sig]

    return {
        "financial_health": {
            "signal": fh_sig,
            "note": _note(fh_sig,
                f"Gross margin {live['gross_margin']*100:.1f}%, FCF positive, net cash ${live['net_cash']/1e9:+.1f}B",
                f"Gross margin {live['gross_margin']*100:.1f}%, some areas need monitoring",
                "Net income or FCF negative — financial stress"),
        },
        "earnings_quality": {
            "signal": eq_sig,
            "note": _note(eq_sig,
                f"FCF ${fcf/1e9:.1f}B closely tracks net income ${ni/1e9:.1f}B — clean",
                f"FCF ${fcf/1e9:.1f}B vs net income ${ni/1e9:.1f}B — gap worth investigating",
                f"FCF ${fcf/1e9:.1f}B well below net income ${ni/1e9:.1f}B — investigate drivers"),
        },
        "competitive_moat": {
            "signal": moat_sig,
            "note": _note(moat_sig,
                f"Gross margin {live['gross_margin']*100:.1f}% + ROE {(live['roe'] or 0)*100:.1f}% suggest strong pricing power",
                f"Moderate margins — some competitive advantage, monitor for erosion",
                "Low margins and ROE suggest limited pricing power or competitive pressure"),
        },
        "valuation": {
            "signal": val_sig,
            "note": _note(val_sig,
                f"Price ${live['current_price']} within or below blended fair value ${round(live['current_price'],0):.0f}",
                f"Price ${live['current_price']} moderately above blended fair value",
                f"Price ${live['current_price']} significantly above blended fair value — limited margin of safety"),
        },
        "market_sentiment": {
            "signal": sent_sig,
            "note": _note(sent_sig,
                f"PE at {pe_res.percentile}th historical percentile — not crowded",
                f"PE at {pe_res.percentile}th percentile — elevated but not extreme",
                f"PE at {pe_res.percentile}th percentile — historically stretched, sentiment risk"),
        },
        "policy_risk": {
            "signal": pol_sig,
            "note": f"Beta {live['beta']:.2f} — {'above' if live['beta'] > 1 else 'below'} market volatility. Country: {live['country']}",
        },
    }


def _top_risk(live: dict, scorecard: dict) -> str:
    reds = [k for k, v in scorecard.items() if v["signal"] == "red"]
    if "valuation" in reds:
        return "valuation stretch — price significantly above fair value model"
    if "financial_health" in reds:
        return "financial health — negative FCF or net income"
    if "market_sentiment" in reds:
        return "sentiment crowding — PE at historically elevated percentile"
    return "monitor scorecard dimensions for deterioration"


def _risk_score(scorecard: dict) -> int:
    weights = {"red": 2, "yellow": 1, "green": 0}
    total = sum(weights.get(v["signal"], 1) for v in scorecard.values())
    return min(10, max(1, round(total * 10 / 12)))


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Generate report
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(report_data: dict, output_path: str) -> str:
    from report_generator import generate_html_report
    print(f"  [4/4] Generating HTML report...")
    return generate_html_report(report_data, output_path)



# ─────────────────────────────────────────────────────────────────────────────
# COMPANY PROFILE — auto-built from yfinance data
# ─────────────────────────────────────────────────────────────────────────────

def _build_company_profile(ticker: str, live: dict) -> dict:
    """
    Build company profile from yfinance longBusinessSummary + structured fields.
    v5.4 schema: deep product edges, hybrid customer format, Commercial Essence prefix.
    """
    import yfinance as yf
    import re

    try:
        info = yf.Ticker(ticker).info
        summary = info.get("longBusinessSummary") or ""
    except Exception:
        info = {}
        summary = ""

    name     = live["company_name"]
    sector   = live["sector"]
    industry = live["industry"]
    country  = live["country"]

    # ── Business (Core Moat Focus) ──
    if summary:
        sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
        business = " ".join(sentences[:2]).strip()
        if len(business) > 320:
            business = business[:317] + "..."
    else:
        business = f"{name} operates in the {industry} industry ({sector}, {country})."

    # ── Products (Tech Edge Tags) — 3-5 deep proprietary names ──
    products = []
    if summary:
        patterns = [
            r"(?:offers|provides|develops|manufactures|sells|delivers|produces)\s+([^,.;]+(?:,\s*[^,.;]+){0,3})",
            r"(?:its\s+)?(?:products?|services?|solutions?|platforms?|systems?)\s+(?:include|such as|:)\s+([^.;]+)",
            r"(?:brands?|technologies?|architectures?|chips?|GPUs?|CPUs?|software\s+platforms?)\s+(?:include|such as|:)\s+([^.;]+)",
        ]
        for pat in patterns:
            m = re.search(pat, summary, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                items = re.split(r",\s*|\s+and\s+|\s*;\s*", raw)
                products = [i.strip().rstrip(".") for i in items if len(i.strip()) > 3][:5]
                if products:
                    break

    if not products:
        if industry:
            products = [industry]
        if sector and sector not in products:
            products.append(sector)
        products = products[:3] if products else ["Core products — see annual report"]

    # ── Customers (Hybrid Format) ──
    customer_map = {
        "Technology":            ["Enterprise clients", "Cloud providers", "Software developers", "OEMs"],
        "Healthcare":            ["Hospitals & health systems", "Insurers", "Patients", "Governments"],
        "Financial Services":    ["Retail banking customers", "Institutional investors", "Corporates", "Wealth clients"],
        "Consumer Cyclical":     ["Individual consumers", "Retail partners", "Distributors"],
        "Consumer Defensive":    ["Individual consumers", "Grocery & retail chains", "Foodservice operators"],
        "Industrials":           ["Industrial manufacturers", "Government & defence", "Infrastructure operators", "Aerospace OEMs"],
        "Energy":                ["Utilities", "Industrial consumers", "Government", "Refiners"],
        "Communication Services":["Consumers", "Enterprises", "Advertisers", "Content creators"],
        "Real Estate":           ["Tenants", "Institutional investors", "REIT sponsors"],
        "Basic Materials":       ["Manufacturers", "Construction companies", "Automotive OEMs"],
        "Utilities":             ["Residential customers", "Commercial businesses", "Government", "Data centers"],
    }

    customers_from_summary = []
    if summary:
        m = re.search(
            r"(?:serves?|customers?\s+include|clients?\s+include|used\s+by)\s+([^.;]+)",
            summary, re.IGNORECASE
        )
        if m:
            raw = m.group(1).strip()
            items = re.split(r",\s*|\s+and\s+", raw)
            customers_from_summary = [i.strip().rstrip(".") for i in items if len(i.strip()) > 3][:4]

    customers_tags = customers_from_summary or customer_map.get(sector, ["Enterprise clients", "Individual consumers", "Government"])
    customers_tags = customers_tags[:4]

    # Customer dynamics sentence (placeholder — enriched by AI layer)
    customers_dynamics = (
        f"Customer base spans {customers_tags[0].lower()} and related segments; "
        f"concentration dynamics should be verified against latest filings."
    )

    # ── Business Model (Monetization Essence) ──
    model_map = {
        "Technology":            "Commercial Essence: Sells software licences, hardware, and/or cloud-based subscriptions. High-margin recurring revenue with platform lock-in potential.",
        "Healthcare":            "Commercial Essence: Sells pharmaceutical products, medical devices, or healthcare services. Revenue tied to regulatory approvals and reimbursement cycles.",
        "Financial Services":    "Commercial Essence: Earns net interest income, fees, and asset management revenue. Capital-intensive with regulatory-constrained leverage.",
        "Consumer Cyclical":     "Commercial Essence: Sells discretionary goods and services directly to consumers. Revenue cyclical — rises and falls with household confidence.",
        "Consumer Defensive":    "Commercial Essence: Sells everyday consumer goods through retail and direct channels. Volume-stable but price-competitive.",
        "Industrials":           "Commercial Essence: Manufactures and sells capital equipment, components, or services to businesses. Long sales cycles with order-backlog visibility.",
        "Energy":                "Commercial Essence: Extracts, refines, or distributes energy commodities. Price-taker on global commodity curves with heavy fixed-cost base.",
        "Communication Services":"Commercial Essence: Provides connectivity, media, or advertising-based revenue streams. Subscriber ARPU and ad load drive monetization.",
        "Real Estate":           "Commercial Essence: Earns rental income and capital gains from property assets. Yield-driven with interest-rate sensitivity.",
        "Basic Materials":       "Commercial Essence: Mines, processes, and sells raw materials to industrial buyers. Cyclical margins driven by global supply/demand balances.",
        "Utilities":             "Commercial Essence: Provides regulated electricity, gas, or water services. Stable, rate-base-driven returns with limited growth optionality.",
    }

    model = ""
    if summary:
        m = re.search(
            r"(?:generates?\s+revenue|earns?\s+(?:revenue|income)|(?:its\s+)?revenue\s+(?:comes?|is\s+generated))\s+(?:from|through|by)\s+([^.;]+)",
            summary, re.IGNORECASE
        )
        if m:
            model = "Commercial Essence: Revenue " + m.group(0).strip().rstrip(".") + "."

    if not model:
        model = model_map.get(sector, f"Commercial Essence: Generates revenue through its {industry} operations.")

    return {
        "business":            business,
        "products":            products,
        "customers_tags":      customers_tags,
        "customers_dynamics":  customers_dynamics,
        "model":               model,
    }
def _build_executive_summary(ticker: str, live: dict, profile: dict,
                                blended: float, gap_str: str, pe_res) -> dict:
    """Build Executive Summary: 2-sentence thesis + 3 development bullets."""

    name    = live["company_name"]
    price   = live["current_price"]
    rev_b   = live["revenue"] / 1e9
    fcf_b   = live["fcf"] / 1e9
    gm      = live["gross_margin"] * 100
    roe     = (live["roe"] or 0) * 100
    pe      = live["pe"]
    biz     = profile.get("business", "")
    if len(biz) > 200:
        biz = biz[:197] + "..."

    # Part A — Core Thesis (2 sentences)
    fcf_desc = "positive" if fcf_b > 0 else "negative (cash burn)"
    gm_desc = "high" if gm > 50 else ("mid-range" if gm > 25 else "thin")
    thesis_sent1 = biz
    thesis_sent2 = (
        f"Financial profile: {gm_desc} gross margins, ${abs(fcf_b):.1f}B FCF ({fcf_desc}), "
        f"ROE {roe:.1f}%."
    )

    # Part B — Latest Developments (3 placeholder bullets — enriched by AI layer)
    gap_num = float(gap_str.replace("%","").replace("+",""))
    val_state = "elevated" if gap_num > 20 else ("neutral" if gap_num > -20 else "compressed")
    developments = [
        f"Valuation currently {val_state} vs blended fair value of ${blended:.0f} — monitor next earnings for guidance revision.",
        f"PE at {pe_res.percentile}th historical percentile; sentiment {'stretched' if pe_res.percentile > 80 else 'moderate'} relative to 5-year range.",
        "Key catalyst watch: analyst consensus drift, sector rotation signals, and macro policy shifts.",
    ]

    return {
        "thesis": [thesis_sent1, thesis_sent2],
        "developments": developments,
    }

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Company Analyst — Generate a full equity research report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze.py AAPL
  python analyze.py NVDA --lang zh
  python analyze.py NOK --no-browser --output reports/nok.html
  python analyze.py 0700.HK --lang zh
        """
    )
    parser.add_argument("ticker",        help="Stock ticker (e.g. AAPL, NVDA, 0700.HK)")
    parser.add_argument("--lang",        default="en", help="Report language: en / zh (default: en)")
    parser.add_argument("--no-browser",  action="store_true", help="Do not open browser after generation")
    parser.add_argument("--output",      default=None, help="Output HTML path (default: {TICKER}_report.html)")
    parser.add_argument("--rf",          type=float, default=0.043, help="Risk-free rate, e.g. 0.043 (default: 4.3%%)")
    parser.add_argument("--json",        action="store_true", help="Also save report data as JSON")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    output = args.output or f"{ticker.replace('.','_')}_report.html"

    print(f"\n{'='*55}")
    print(f"  Company Analyst v5.4 — {ticker}")
    print(f"{'='*55}")

    try:
        # Step 1: Live data
        live = fetch_live_data(ticker)
        print(f"        {live['company_name']} | ${live['current_price']} | {live['exchange']}")

        # Step 2: Valuation
        val = run_valuation(ticker, live, rf_rate=args.rf)

        # Step 3: Build report data
        report_data = build_report_data(ticker, live, val, lang=args.lang)

        # Optionally save JSON
        if args.json:
            json_path = output.replace(".html", "_data.json")
            with open(json_path, "w") as f:
                json.dump(report_data, f, indent=2, default=str)
            print(f"        Data saved → {json_path}")

        # Step 4: Generate HTML
        generate_report(report_data, output)

        print(f"\n{'='*55}")
        print(f"  ✅ Report ready: {output}")
        print(f"  📊 {ticker} | ${live['current_price']} | Fair value: ${val['blended_fv']:.0f}")
        print(f"  📈 PE: {live['pe']:.1f}x at {val['pe_res'].percentile}th percentile" if live["pe"] else "")
        print(f"{'='*55}\n")

        # Open browser
        if not args.no_browser:
            abs_path = os.path.abspath(output)
            webbrowser.open(f"file://{abs_path}")

    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
