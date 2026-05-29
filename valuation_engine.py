"""
valuation_engine.py v2.0
Three upgraded modules:
  1. pe_percentile()    — real 5-year historical PE percentile
  2. dynamic_dcf()      — analyst-consensus-anchored DCF scenarios
  3. comps_valuation()  — relative valuation vs sector peers
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1: Real 5-Year PE Historical Percentile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PEPercentileResult:
    current_pe: float
    pe_5yr_median: float
    pe_5yr_min: float
    pe_5yr_max: float
    percentile: int                  # 0–100
    premium_to_median_pct: float    # e.g. +65% means 65% above 5yr median
    label: str                       # EXTREME GREED / WARM / NEUTRAL / FEARFUL
    color: str                       # hex
    plain_text: str                  # one sentence for the report


def pe_percentile(ticker: str) -> PEPercentileResult:
    """
    Fetch 5 years of monthly price history and trailing EPS,
    reconstruct a monthly PE series, compute percentile of current PE.
    """
    import yfinance as yf

    stock  = yf.Ticker(ticker)
    info   = stock.info
    hist   = stock.history(period="5y", interval="1mo")

    current_pe = info.get("trailingPE", None)
    eps_ttm    = info.get("trailingEps", None)

    if hist.empty or eps_ttm is None or eps_ttm <= 0:
        return _pe_fallback(current_pe)

    # Reconstruct historical PE: monthly close / trailing EPS at that time.
    # yfinance doesn't give historical EPS, so we use a simplified approach:
    # treat current EPS as constant (conservative — understates past PE when
    # earnings were lower, overstates when earnings were higher).
    # For a more accurate calc, use quarterly EPS from income statements.
    try:
        quarterly = stock.quarterly_income_stmt
        if quarterly is not None and not quarterly.empty and "Net Income" in quarterly.index:
            # Build trailing 4-quarter EPS series aligned to monthly dates
            ni_q = quarterly.loc["Net Income"].sort_index()
            shares = info.get("sharesOutstanding", None)
            if shares and shares > 0:
                eps_q = ni_q / shares
                # Rolling 4-quarter sum = TTM EPS at each quarter end
                eps_ttm_series = eps_q.rolling(4).sum().dropna()
                # Resample monthly close to match
                monthly_close = hist["Close"].resample("QE").last()
                # Align
                common_idx = monthly_close.index.intersection(eps_ttm_series.index)
                if len(common_idx) >= 8:
                    pe_series = monthly_close[common_idx] / eps_ttm_series[common_idx]
                    pe_series = pe_series[pe_series > 0].dropna()
                    return _compute_result(current_pe, pe_series)
    except Exception:
        pass

    # Fallback: use current EPS across all history
    closes = hist["Close"].dropna()
    if eps_ttm > 0:
        pe_series = closes / eps_ttm
        pe_series = pe_series[pe_series > 0]
        return _compute_result(current_pe, pe_series)

    return _pe_fallback(current_pe)


def _compute_result(current_pe, pe_series) -> PEPercentileResult:
    if current_pe is None or len(pe_series) < 4:
        return _pe_fallback(current_pe)

    arr     = np.array(pe_series.values, dtype=float)
    pct     = int(np.round(np.sum(arr <= current_pe) / len(arr) * 100))
    median  = float(np.median(arr))
    mn      = float(np.min(arr))
    mx      = float(np.max(arr))
    premium = round((current_pe - median) / median * 100, 1) if median > 0 else 0

    if pct > 85:
        label = "EXTREME GREED"; color = "#ef4444"
        text  = (f"Current PE ({current_pe:.1f}x) is at the {pct}th percentile of the past 5 years "
                 f"({premium:+.0f}% above the 5yr median of {median:.1f}x). "
                 f"You are paying a premium for sentiment, not for fundamentals.")
    elif pct > 60:
        label = "WARM"; color = "#eab308"
        text  = (f"Current PE ({current_pe:.1f}x) is at the {pct}th percentile. "
                 f"Elevated vs the 5yr median ({median:.1f}x) — growth expectations are baked in.")
    elif pct > 40:
        label = "NEUTRAL"; color = "#6366f1"
        text  = (f"Current PE ({current_pe:.1f}x) is at the {pct}th percentile — "
                 f"close to the 5yr median ({median:.1f}x). Market is pricing fundamentals fairly.")
    else:
        label = "FEARFUL"; color = "#22c55e"
        text  = (f"Current PE ({current_pe:.1f}x) is at the {pct}th percentile — "
                 f"compressed vs the 5yr median ({median:.1f}x). "
                 f"Market may be underpricing. Verify fundamentals haven't deteriorated.")

    return PEPercentileResult(
        current_pe=round(current_pe, 1),
        pe_5yr_median=round(median, 1),
        pe_5yr_min=round(mn, 1),
        pe_5yr_max=round(mx, 1),
        percentile=pct,
        premium_to_median_pct=premium,
        label=label, color=color, plain_text=text,
    )


def _pe_fallback(current_pe) -> PEPercentileResult:
    return PEPercentileResult(
        current_pe=current_pe or 0,
        pe_5yr_median=0, pe_5yr_min=0, pe_5yr_max=0,
        percentile=50, premium_to_median_pct=0,
        label="N/A", color="#888",
        plain_text="Historical PE data unavailable — percentile could not be computed.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2: Dynamic DCF Anchored to Analyst Consensus
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DCFScenario:
    name: str
    revenue_growth_rates: list[float]   # year-by-year for 5 years
    fcf_margin: float
    wacc: float
    terminal_growth: float
    equity_value_bn: float = 0.0
    price_per_share: float = 0.0


@dataclass
class DynamicDCFResult:
    scenarios: list[DCFScenario]
    base_growth_source: str             # "analyst consensus" or "yfinance estimate" or "revenue trend"
    consensus_growth_yr1: Optional[float]
    wacc_used: float
    wacc_basis: str                     # e.g. "CAPM: Rf=4.3% β=2.24 ERP=5%"
    sensitivity: dict                   # wacc_labels, tgr_labels, equity_value_bn matrix
    net_debt: float


def dynamic_dcf(ticker: str, rf_rate: float = 0.043, erp: float = 0.05) -> DynamicDCFResult:
    """
    1. Pull analyst consensus EPS/revenue growth estimate
    2. Use as Base scenario; +30% = Bull, -30% = Bear
    3. WACC calibrated via CAPM using real Beta
    4. Run DCF and sensitivity matrix
    """
    import yfinance as yf

    stock = yf.Ticker(ticker)
    info  = stock.info

    # ── WACC via CAPM ──
    beta = info.get("beta", 1.0) or 1.0
    cost_of_equity = rf_rate + beta * erp
    # Assume 70% equity weight for most tech; adjust for high-debt companies
    total_debt = info.get("totalDebt", 0) or 0
    mkt_cap    = info.get("marketCap", 1) or 1
    ev         = mkt_cap + total_debt
    eq_weight  = mkt_cap / ev
    debt_weight = total_debt / ev
    cost_of_debt = info.get("payoutRatio", 0.04) or 0.04  # rough proxy
    if cost_of_debt < 0.01 or cost_of_debt > 0.15:
        cost_of_debt = 0.04
    tax_rate = 0.21
    wacc = eq_weight * cost_of_equity + debt_weight * cost_of_debt * (1 - tax_rate)
    wacc = max(0.07, min(0.20, round(wacc, 3)))
    wacc_basis = (f"CAPM: Rf={rf_rate*100:.1f}% β={beta:.2f} ERP={erp*100:.0f}% "
                  f"→ CoE={cost_of_equity*100:.1f}% → WACC={wacc*100:.1f}%")

    # ── Base revenue data ──
    base_revenue = info.get("totalRevenue", 0) or 0
    fcf          = info.get("freeCashflow", 0) or 0
    fcf_margin   = (fcf / base_revenue) if base_revenue > 0 else 0.15
    fcf_margin   = max(0.05, min(0.60, fcf_margin))
    net_debt     = (info.get("totalDebt", 0) or 0) - (info.get("totalCash", 0) or 0)
    shares       = info.get("sharesOutstanding", 1) or 1

    # ── Analyst consensus growth (yr 1) ──
    consensus_g = None
    source      = "revenue trend (5yr CAGR)"
    try:
        # Try earnings estimates
        est = stock.earnings_estimate
        if est is not None and not est.empty and "growth" in est.columns:
            g_row = est.loc["0y"] if "0y" in est.index else est.iloc[0]
            consensus_g = float(g_row["growth"])
            source = "analyst EPS growth consensus"
    except Exception:
        pass

    if consensus_g is None:
        try:
            ge = stock.growth_estimates
            if ge is not None and not ge.empty:
                if "NVDA" in ge.columns:
                    val = ge["NVDA"].get("Next 5 Years (per annum)", None)
                    if val: consensus_g = float(val); source = "analyst 5yr growth estimate"
        except Exception:
            pass

    if consensus_g is None:
        # Fallback: compute 3yr revenue CAGR from income statement
        try:
            inc = stock.income_stmt
            if inc is not None and not inc.empty and "Total Revenue" in inc.index:
                revs = inc.loc["Total Revenue"].dropna().sort_index()
                if len(revs) >= 2:
                    oldest, newest = float(revs.iloc[0]), float(revs.iloc[-1])
                    n = len(revs) - 1
                    cagr = (newest / oldest) ** (1 / n) - 1 if oldest > 0 else 0.15
                    consensus_g = min(max(cagr, 0.03), 0.60)
                    source = f"revenue CAGR ({n}yr)"
        except Exception:
            pass

    if consensus_g is None:
        consensus_g = 0.12
        source = "default estimate (data unavailable)"

    consensus_g = max(0.02, min(0.80, consensus_g))

    # ── Build 5-year growth paths ──
    def growth_path(yr1: float, decay: float = 0.85) -> list[float]:
        """Geometric decay from yr1."""
        g = yr1
        path = []
        for _ in range(5):
            path.append(round(g, 3))
            g *= decay
        return path

    bull_g  = min(consensus_g * 1.30, 0.80)
    base_g  = consensus_g
    bear_g  = max(consensus_g * 0.70, 0.02)

    # Terminal growth: lower for faster growers (reversion to mean)
    tg_bull = 0.04 if bull_g > 0.30 else 0.035
    tg_base = 0.03
    tg_bear = 0.02

    scenarios_raw = [
        ("Bull", growth_path(bull_g, 0.88), tg_bull, wacc * 0.95),
        ("Base", growth_path(base_g, 0.85), tg_base, wacc),
        ("Bear", growth_path(bear_g, 0.80), tg_bear, wacc * 1.05),
    ]

    results = []
    for name, gr, tg, w in scenarios_raw:
        ev_val, px = _run_single_dcf(base_revenue, fcf_margin, gr, w, tg, net_debt, shares)
        results.append(DCFScenario(
            name=name, revenue_growth_rates=gr, fcf_margin=fcf_margin,
            wacc=round(w, 3), terminal_growth=tg,
            equity_value_bn=round(ev_val / 1e9, 1),
            price_per_share=round(px, 2),
        ))

    # ── Sensitivity matrix ──
    wacc_range = [round(wacc - 0.02 + i * 0.01, 2) for i in range(5)]
    tgr_range  = [0.02, 0.025, 0.03, 0.035, 0.04]
    matrix = []
    for w in wacc_range:
        row = []
        for tg in tgr_range:
            ev_v, _ = _run_single_dcf(base_revenue, fcf_margin,
                                       growth_path(base_g), w, tg, net_debt, shares)
            row.append(round(ev_v / 1e9, 1))
        matrix.append(row)

    sensitivity = {
        "wacc_labels": [f"{int(w*100)}%" for w in wacc_range],
        "tgr_labels":  [f"{int(tg*1000)/10:.1f}%" for tg in tgr_range],
        "equity_value_bn": matrix,
    }

    return DynamicDCFResult(
        scenarios=results,
        base_growth_source=source,
        consensus_growth_yr1=round(consensus_g * 100, 1),
        wacc_used=wacc,
        wacc_basis=wacc_basis,
        sensitivity=sensitivity,
        net_debt=net_debt,
    )


def _run_single_dcf(base_rev, fcf_margin, growth_rates, wacc, terminal_g, net_debt, shares):
    rev = base_rev
    pv_fcfs = []
    for i, g in enumerate(growth_rates):
        rev *= (1 + g)
        fcf = rev * fcf_margin
        pv  = fcf / (1 + wacc) ** (i + 1)
        pv_fcfs.append(pv)

    terminal_fcf = rev * fcf_margin * (1 + terminal_g)
    if wacc <= terminal_g:
        wacc = terminal_g + 0.01
    tv  = terminal_fcf / (wacc - terminal_g)
    pv_tv = tv / (1 + wacc) ** len(growth_rates)

    enterprise_value = sum(pv_fcfs) + pv_tv
    equity_value     = enterprise_value - net_debt
    price_per_share  = equity_value / shares if shares > 0 else 0
    return equity_value, price_per_share


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 3: Relative Valuation (Comps)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompsResult:
    subject_ticker: str
    subject_metrics: dict               # pe, ev_ebitda, peg, pb, ps
    peers: list[dict]                   # [{ticker, name, pe, ev_ebitda, peg, ...}]
    peer_medians: dict
    premium_discount: dict              # {metric: pct vs median}
    implied_price_range: dict           # {metric: implied_price}
    blended_fair_value: float           # average of implied prices
    summary: str                        # one-sentence plain text


# Sector peer maps — expand as needed
SECTOR_PEERS = {
    "semiconductors": ["NVDA","AMD","INTC","QCOM","AVGO","TSM","MU","AMAT","LRCX","KLAC"],
    "cloud_software":  ["MSFT","AMZN","GOOGL","CRM","NOW","SNOW","DDOG","MDB"],
    "consumer_tech":   ["AAPL","META","SNAP","PINS","TWTR"],
    "ev_auto":         ["TSLA","GM","F","NIO","LI","RIVN"],
    "financials":      ["JPM","BAC","GS","MS","WFC","C"],
}

TICKER_SECTOR = {
    "NVDA":"semiconductors","AMD":"semiconductors","INTC":"semiconductors",
    "QCOM":"semiconductors","AVGO":"semiconductors","TSM":"semiconductors",
    "MSFT":"cloud_software","AMZN":"cloud_software","GOOGL":"cloud_software",
    "CRM":"cloud_software","NOW":"cloud_software",
    "AAPL":"consumer_tech","META":"consumer_tech",
    "TSLA":"ev_auto","GM":"ev_auto","F":"ev_auto",
    "JPM":"financials","BAC":"financials","GS":"financials",
}


def comps_valuation(ticker: str, custom_peers: list[str] = None) -> CompsResult:
    """
    Fetch PE, EV/EBITDA, PEG, P/B, P/S for subject and peer group.
    Compute medians, premium/discount, and implied price from each multiple.
    """
    import yfinance as yf

    sector   = TICKER_SECTOR.get(ticker.upper(), "semiconductors")
    all_peers = custom_peers or SECTOR_PEERS.get(sector, [])
    peers_tickers = [p for p in all_peers if p.upper() != ticker.upper()][:6]

    def _fetch_metrics(t: str) -> dict:
        try:
            info = yf.Ticker(t).info
            price    = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            mktcap   = info.get("marketCap") or 0
            ebitda   = info.get("ebitda") or 0
            ev       = mktcap + (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)
            revenue  = info.get("totalRevenue") or 0
            shares   = info.get("sharesOutstanding") or 1
            bv_share = (info.get("bookValue") or 0)
            pe       = info.get("trailingPE") or None
            peg      = info.get("pegRatio") or None
            ev_ebitda = round(ev / ebitda, 1) if ebitda and ebitda > 0 else None
            pb       = round(price / bv_share, 1) if bv_share and bv_share > 0 else None
            ps       = round(mktcap / revenue, 1) if revenue and revenue > 0 else None
            eps      = info.get("trailingEps") or None
            return {
                "ticker": t,
                "name":   info.get("shortName", t),
                "price":  round(price, 2),
                "pe":     round(pe, 1) if pe else None,
                "ev_ebitda": ev_ebitda,
                "peg":    round(peg, 2) if peg else None,
                "pb":     pb,
                "ps":     ps,
                "eps":    round(eps, 2) if eps else None,
                "revenue": revenue,
                "ebitda":  ebitda,
                "shares":  shares,
                "ev":      ev,
            }
        except Exception:
            return {"ticker": t, "name": t, "pe": None, "ev_ebitda": None,
                    "peg": None, "pb": None, "ps": None}

    subject = _fetch_metrics(ticker)
    peers   = [_fetch_metrics(p) for p in peers_tickers]
    peers   = [p for p in peers if p.get("pe") or p.get("ev_ebitda")]

    # Peer medians
    def _median(lst): 
        vals = [x for x in lst if x is not None]
        return round(float(np.median(vals)), 1) if vals else None

    peer_medians = {
        "pe":        _median([p["pe"] for p in peers]),
        "ev_ebitda": _median([p["ev_ebitda"] for p in peers]),
        "peg":       _median([p["peg"] for p in peers]),
        "pb":        _median([p["pb"] for p in peers]),
        "ps":        _median([p["ps"] for p in peers]),
    }

    # Premium / discount vs peer median
    def _prem(subj_val, med):
        if subj_val and med and med > 0:
            return round((subj_val - med) / med * 100, 1)
        return None

    premium_discount = {
        k: _prem(subject.get(k), peer_medians.get(k))
        for k in ["pe","ev_ebitda","peg","pb","ps"]
    }

    # Implied price from each multiple (back-solve: what price would put subject at peer median?)
    implied = {}
    price    = subject.get("price") or 0
    eps      = subject.get("eps") or 0
    ebitda   = subject.get("ebitda") or 0
    revenue  = subject.get("revenue") or 0
    shares   = subject.get("shares") or 1
    ev       = subject.get("ev") or 0
    net_debt = ev - (subject.get("price", 0) * shares)

    if peer_medians["pe"] and eps and eps > 0:
        implied["pe"] = round(peer_medians["pe"] * eps, 2)

    if peer_medians["ev_ebitda"] and ebitda and ebitda > 0:
        impl_ev  = peer_medians["ev_ebitda"] * ebitda
        impl_eq  = impl_ev - net_debt
        implied["ev_ebitda"] = round(impl_eq / shares, 2) if shares > 0 else None

    if peer_medians["ps"] and revenue and revenue > 0:
        impl_mktcap = peer_medians["ps"] * revenue
        implied["ps"] = round(impl_mktcap / shares, 2) if shares > 0 else None

    # Blended fair value (average of available implied prices)
    impl_vals = [v for v in implied.values() if v and v > 0]
    blended   = round(float(np.mean(impl_vals)), 2) if impl_vals else 0.0

    # Summary sentence
    prem_pe = premium_discount.get("pe")
    if prem_pe is not None:
        direction = "premium" if prem_pe > 0 else "discount"
        summary = (f"{ticker} trades at a {abs(prem_pe):.0f}% {direction} to sector peers "
                   f"on PE ({subject.get('pe', '—')}x vs median {peer_medians['pe']}x). "
                   f"Peer-median-implied price: ${blended:.0f} "
                   f"({'+' if price > blended else ''}{((price - blended)/blended*100):.0f}% vs current).")
    else:
        summary = f"Peer comparison computed. Blended implied price: ${blended:.0f}."

    return CompsResult(
        subject_ticker=ticker,
        subject_metrics={k: subject.get(k) for k in ["pe","ev_ebitda","peg","pb","ps","price"]},
        peers=peers,
        peer_medians=peer_medians,
        premium_discount=premium_discount,
        implied_price_range=implied,
        blended_fair_value=blended,
        summary=summary,
    )


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FullValuation:
    pe_result:   PEPercentileResult
    dcf_result:  DynamicDCFResult
    comps_result: CompsResult
    combined_fair_value: float      # weighted average: 50% DCF base + 30% comps + 20% DCF bear
    combined_summary: str


def full_valuation(ticker: str, rf_rate: float = 0.043) -> FullValuation:
    """Run all three modules and combine into a single valuation object."""
    print(f"[1/3] Computing PE percentile for {ticker}...")
    pe_res = pe_percentile(ticker)

    print(f"[2/3] Running dynamic DCF for {ticker}...")
    dcf_res = dynamic_dcf(ticker, rf_rate=rf_rate)

    print(f"[3/3] Running comps valuation for {ticker}...")
    try:
        comps_res = comps_valuation(ticker)
    except Exception as e:
        print(f"  Comps failed: {e} — using DCF-only blended value")
        comps_res = None

    # Blended fair value: 50% DCF base + 30% comps + 20% DCF bear
    dcf_base  = next((s.price_per_share for s in dcf_res.scenarios if s.name == "Base"), 0)
    dcf_bear  = next((s.price_per_share for s in dcf_res.scenarios if s.name == "Bear"), 0)
    comps_fv  = comps_res.blended_fair_value if comps_res else 0

    if comps_fv > 0:
        blended = round(0.50 * dcf_base + 0.30 * comps_fv + 0.20 * dcf_bear, 2)
        method  = "50% DCF Base + 30% Peer Comps + 20% DCF Bear"
    else:
        blended = round(0.70 * dcf_base + 0.30 * dcf_bear, 2)
        method  = "70% DCF Base + 30% DCF Bear (comps unavailable)"

    summary = (
        f"Three-method valuation: DCF Base ${dcf_base:.0f} | "
        f"Peer Comps ${comps_fv:.0f} | "
        f"Blended fair value ${blended:.0f} ({method}). "
        f"PE sentiment: {pe_res.label} ({pe_res.percentile}th percentile)."
    )

    if comps_res is None:
        import dataclasses
        comps_res = CompsResult(
            subject_ticker=ticker, subject_metrics={}, peers=[],
            peer_medians={}, premium_discount={}, implied_price_range={},
            blended_fair_value=0.0, summary="Comps data unavailable.",
        )

    return FullValuation(
        pe_result=pe_res, dcf_result=dcf_res, comps_result=comps_res,
        combined_fair_value=blended, combined_summary=summary,
    )


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION HELPER: convert FullValuation → report_generator data dict
# ─────────────────────────────────────────────────────────────────────────────

def valuation_to_report_data(ticker: str, fv: FullValuation,
                              current_price: float, date: str) -> dict:
    """
    Convert FullValuation output into the data dict expected by
    report_generator.generate_html_report().
    """
    import yfinance as yf
    info = yf.Ticker(ticker).info

    dcf  = fv.dcf_result
    pe   = fv.pe_result
    comp = fv.comps_result

    dcf_scenarios = [
        {"scenario": s.name,
         "equity_value_bn": s.equity_value_bn,
         "price_per_share": s.price_per_share}
        for s in dcf.scenarios
    ]

    base_price = next(
        (s.price_per_share for s in dcf.scenarios if s.name == "Base"), 0)
    gap_pct = round((current_price - base_price) / base_price * 100, 0) if base_price > 0 else 0
    gap_str = f"+{int(gap_pct)}%" if gap_pct >= 0 else f"{int(gap_pct)}%"

    # Comps table for report (optional section)
    comps_table = {
        "subject":      comp.subject_metrics,
        "peers":        comp.peers[:5],
        "medians":      comp.peer_medians,
        "premium":      comp.premium_discount,
        "implied":      comp.implied_price_range,
        "blended_fv":   comp.blended_fair_value,
        "summary":      comp.summary,
    }

    return {
        "ticker":          ticker,
        "company_name":    info.get("longName", ticker),
        "date":            date,
        "current_price":   current_price,
        "valuation_percentile": pe.percentile,
        "pe_detail": {
            "current":          pe.current_pe,
            "median_5yr":       pe.pe_5yr_median,
            "min_5yr":          pe.pe_5yr_min,
            "max_5yr":          pe.pe_5yr_max,
            "premium_to_median": pe.premium_to_median_pct,
            "label":            pe.label,
            "color":            pe.color,
            "plain_text":       pe.plain_text,
        },
        "dcf_scenarios":   dcf_scenarios,
        "sensitivity":     dcf.sensitivity,
        "dcf_meta": {
            "base_growth_source":   dcf.base_growth_source,
            "consensus_growth_yr1": dcf.consensus_growth_yr1,
            "wacc":                 dcf.wacc_used,
            "wacc_basis":           dcf.wacc_basis,
        },
        "comps":           comps_table,
        "combined_fair_value": fv.combined_fair_value,
        "combined_summary":    fv.combined_summary,
        "price_anchor": {
            "current_price": current_price,
            "fair_value":    round(fv.combined_fair_value, 2),
            "dcf_base":      base_price,
            "comps_fv":      comp.blended_fair_value,
            "gap_pct":       gap_str,
            "gap_label": (
                f"Market price is {gap_str} above the blended fair value "
                f"(50% DCF Base + 30% Peer Comps + 20% DCF Bear = ${fv.combined_fair_value:.0f}). "
                f"This is not a prediction — it is a reference point."
                if gap_pct > 0 else
                f"Market price is {gap_str} below blended fair value — "
                f"a potential margin of safety. Verify fundamentals are intact."
            ),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, datetime

    TICKER = "NVDA"
    print(f"\n{'='*60}")
    print(f"  Full Valuation Engine — {TICKER}")
    print(f"{'='*60}\n")

    fv = full_valuation(TICKER)

    print(f"\n── PE Percentile ──────────────────────────────")
    print(f"  Current PE:       {fv.pe_result.current_pe}x")
    print(f"  5yr Median PE:    {fv.pe_result.pe_5yr_median}x")
    print(f"  Percentile:       {fv.pe_result.percentile}th")
    print(f"  Label:            {fv.pe_result.label}")
    print(f"  Text:             {fv.pe_result.plain_text[:80]}...")

    print(f"\n── Dynamic DCF ────────────────────────────────")
    print(f"  Growth source:    {fv.dcf_result.base_growth_source}")
    print(f"  Base growth yr1:  {fv.dcf_result.consensus_growth_yr1}%")
    print(f"  WACC:             {fv.dcf_result.wacc_basis}")
    for s in fv.dcf_result.scenarios:
        print(f"  {s.name:5s}: EV ${s.equity_value_bn:.0f}B  |  ${s.price_per_share:.2f}/sh  "
              f"|  yr1 growth {s.revenue_growth_rates[0]*100:.0f}%")

    print(f"\n── Comps Valuation ────────────────────────────")
    print(f"  Summary: {fv.comps_result.summary}")
    print(f"  Implied prices: {fv.comps_result.implied_price_range}")

    print(f"\n── Combined ────────────────────────────────────")
    print(f"  Blended fair value: ${fv.combined_fair_value:.2f}")
    print(f"  {fv.combined_summary}")
