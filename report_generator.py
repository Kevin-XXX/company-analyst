"""report_generator.py v5.4"""

def generate_html_report(data: dict, output_path: str = "report.html"):
    html = _build_html(data)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved -> {output_path}")
    return output_path

def _tc(l): return {"cold":"#38bdf8","normal":"#22c55e","warm":"#eab308","hot":"#ef4444"}.get(l,"#888")

def _valuation_state(gap_raw):
    try: g = float(str(gap_raw).replace("%","").replace("+",""))
    except: g = 0
    if g > 100:   return ("overvalued", "#f97316",
        "Priced for perfection — the multiple already discounts the most optimistic scenario, leaving zero room for operational error.")
    elif g > 20:  return ("elevated",   "#eab308",
        "Trading at a significant momentum premium — current pricing demands flawless execution and leaves little margin for error.")
    elif g > -20: return ("neutral",    "#6366f1",
        "Trading in line with model fair value — valuation is balanced, with neither a clear cushion nor an obvious stretch.")
    else:         return ("undervalued","#22c55e",
        "Trading below model fair value — a structural margin of safety may be present; confirm fundamentals have not deteriorated.")

def _participation_options(state):
    return {
        "overvalued":  ["Scale in via strict dollar-cost averaging — do not deploy full capital at current multiples","Cap single-name exposure (<=5% of portfolio) and pre-define a hard technical stop near the historical drawdown ceiling","Maintain a defensive stance until the next earnings call confirms growth durability"],
        "elevated":    ["Build in small tranches only — avoid full deployment at a premium multiple","Set a hard stop-loss anchored to the historical drawdown ceiling before entering","Wait for the upcoming earnings print to confirm the growth trajectory before sizing up"],
        "neutral":     ["Accumulate across 2-3 tranches over 1-2 months to neutralize timing risk","Pre-define both an upside target and a thesis-invalidation level","Keep position sizing moderate until a clearer catalyst or dislocation appears"],
        "undervalued": ["Confirm fundamentals are intact before treating the discount as opportunity","Accumulate in 2-3 tranches and keep dry powder for further drawdowns","Size for the possibility that a falling price keeps falling — discipline over conviction"],
    }.get(state, [])

def _emotion_meter(percentile):
    if percentile is None: return ("—","#888","No valuation percentile data available.")
    if percentile > 85: return (f"{percentile}th — EXTREME GREED","#ef4444","You are paying a premium for other investors' enthusiasm, not for the company's baseline fundamentals.")
    if percentile > 60: return (f"{percentile}th — WARM","#eab308","Sentiment is elevated. Good news may already be priced in.")
    if percentile > 40: return (f"{percentile}th — NEUTRAL","#6366f1","Market is pricing the company close to fundamentals.")
    return (f"{percentile}th — FEARFUL","#22c55e","Market may be underpricing. Verify fundamentals haven't deteriorated.")

def _sentiment_check(percentile, bull_px, bear_px):
    if percentile is None: return ""
    if percentile > 85:
        return (f'<div class="sent-check hot"><span class="sc-icon">⚠</span>'
                f'<div><strong>Sentiment Alert</strong> — P/E at {percentile}th historical percentile. '
                f'Current price aligns only with the hyper-optimistic Bull scenario (${bull_px}), '
                f'leaving zero margin of safety if growth decelerates.</div></div>')
    if percentile < 40:
        return (f'<div class="sent-check cool"><span class="sc-icon">💡</span>'
                f'<div><strong>Sentiment Opportunity</strong> — P/E compressed at {percentile}th percentile. '
                f'Downside may be cushioned near the Bear scenario (${bear_px}), '
                f'offering potential margin of safety for long-term investors.</div></div>')
    return (f'<div class="sent-check mid"><span class="sc-icon">📊</span>'
            f'<div><strong>Sentiment Moderate</strong> — P/E at {percentile}th percentile. '
            f'Elevated but not extreme — growth expectations are baked in but not hysterical.</div></div>')

SC_PLAIN = {
    "financial_health":  {"green":"Business generates strong profits and real cash.","yellow":"Financials are OK but one area needs watching.","red":"Serious financial concerns — understand these before investing."},
    "earnings_quality":  {"green":"Cash flow tracks reported profits — numbers are trustworthy.","yellow":"Some gap between reported profit and real cash — worth understanding why.","red":"Cash flow well below reported profit — investigate before trusting the headline number."},
    "competitive_moat":  {"green":"A durable advantage competitors can't easily replicate.","yellow":"Some edge exists, but it could erode over time.","red":"No clear sustainable advantage — vulnerable to competition."},
    "valuation":         {"green":"Not overpaying relative to fundamentals — you have some cushion.","yellow":"Fairly valued — not a bargain, not obviously overpriced.","red":"No margin of safety. If growth slows, you bought at the top."},
    "market_sentiment":  {"green":"Investor sentiment is calm — not a crowded trade.","yellow":"Sentiment is warm. Many bullish, which limits upside surprise.","red":"Extremely crowded. High risk of sharp reversal on any disappointment."},
    "policy_risk":       {"green":"No significant regulatory or macro headwinds at this time.","yellow":"Some policy or macro risk on the horizon — monitor it.","red":"Active risk that could directly hit revenue or valuation."},
}
SC_COLOR  = {"green":"#22c55e","yellow":"#eab308","red":"#ef4444"}
SC_LABEL  = {"green":"Strong","yellow":"Moderate","red":"Weak"}
OVERALL_LABEL = {"overvalued":("Overvalued","#f97316"),"elevated":("Elevated / Neutral Border","#eab308"),"neutral":("Neutral","#6366f1"),"undervalued":("Undervalued","#22c55e")}

JARGON = {
    "Free Cash Flow": "Cash left after running and investing in the business. The truest measure of profitability.",
    "FCF Margin":     "Of every $1 revenue, how much becomes real cash. Above 15% = excellent.",
    "ROE":            "Profit per $1 of shareholder equity. Above 15% = strong.",
    "ROIC":           "How efficiently capital turns into profit. Above 10% = money well deployed.",
    "Gross Margin":   "Revenue minus cost of goods. Higher = more pricing power.",
    "Interest Coverage": "How many times profit covers interest. Above 3x = debt is manageable.",
    "PEG Ratio":      "PE divided by growth rate. Below 1.0 may indicate undervaluation.",
    "EV/EBITDA":      "Enterprise value vs operating earnings. Harder to manipulate than PE.",
}

def _tip(metric):
    t = next((v for k,v in JARGON.items() if k.lower() in metric.lower()),"")
    return f'<span class="tip" title="{t}">?</span>' if t else ""

def _build_html(d):
    ticker        = d.get("ticker","—")
    company_name  = d.get("company_name", ticker)
    date          = d.get("date","")
    financials    = d.get("financials",{})
    dcf           = d.get("dcf_scenarios",[])
    sensitivity   = d.get("sensitivity",{})
    scorecard     = d.get("scorecard",{})
    market_temp   = d.get("market_temp",{})
    conclusion    = d.get("analyst_conclusion",{})
    margins       = d.get("margins",{})
    current_price = d.get("current_price", None)
    executive_summary = d.get("executive_summary", {
        "thesis": ["Investment thesis placeholder.","Financial profile summary."],
        "developments": ["Catalyst 1.","Catalyst 2.","Catalyst 3."],
    })
    bull_case     = d.get("bull_case", {"target_price": 0, "points": ["Bull catalyst 1.","Bull catalyst 2."]})
    bear_case     = d.get("bear_case", {"target_price": 0, "points": ["Bear trigger 1.","Bear trigger 2."]})
    valuation_anchor = d.get("valuation_anchor", "The current price reflects market expectations that should be verified against the modelled fair-value range.")
    key_risk      = d.get("key_risk", "Execution or competitive risk that undermines the forward growth assumption.")
    price_anchor  = d.get("price_anchor",{})
    profile       = d.get("company_profile",{})
    valuation_pct = d.get("valuation_percentile", None)
    hist_dd       = d.get("historical_drawdowns",{})
    risk_score    = d.get("risk_score", None)
    triggers      = d.get("condition_triggers",[])
    fact1         = d.get("fact_business","")
    fact2         = d.get("fact_valuation","")
    fact3         = d.get("fact_risk","")

    gm  = margins.get("gross_margin",0)
    fcm = margins.get("fcf_margin",0)
    nm  = margins.get("net_margin",0)

    gap_raw = price_anchor.get("gap_pct","0")
    val_state, val_color, val_text = _valuation_state(gap_raw)
    overall_lbl, overall_col = OVERALL_LABEL.get(val_state,("Neutral","#6366f1"))

    bull_px = next((s.get("price_per_share","—") for s in dcf if s.get("scenario")=="Bull"),"—")
    bear_px = next((s.get("price_per_share","—") for s in dcf if s.get("scenario")=="Bear"),"—")
    em_label, em_color, em_desc = _emotion_meter(valuation_pct)
    sent_check = _sentiment_check(valuation_pct, bull_px, bear_px)
    meter_pct = min(valuation_pct or 50, 100)

    dcf_labels = str([s.get("scenario","") for s in dcf])
    dcf_values = str([s.get("equity_value_bn",0) for s in dcf])
    dcf_prices = str([s.get("price_per_share",0) for s in dcf])

    # Sensitivity heatmap
    wacc_labels = sensitivity.get("wacc_labels",[])
    tgr_labels  = sensitivity.get("tgr_labels",[])
    matrix      = sensitivity.get("equity_value_bn",[])
    all_vals    = [v for row in matrix for v in row] or [0]
    vmin,vmax   = min(all_vals),max(all_vals)
    def cbg(v):
        t=(v-vmin)/(vmax-vmin) if vmax!=vmin else 0.5
        return f"rgba({int(239-t*205)},{int(68+t*129)},{int(68+t*26)},0.85)"
    def cfg(v): return "#fff" if (v-vmin)/(vmax-vmin if vmax!=vmin else 1)<0.55 else "#111"
    heat = "<tr><th>WACC</th>"+"".join(f"<th>{t}</th>" for t in tgr_labels)+"</tr>"
    for i,row in enumerate(matrix):
        heat += "<tr><th>"+(wacc_labels[i] if i<len(wacc_labels) else "")+"</th>"
        heat += "".join(f'<td style="background:{cbg(v)};color:{cfg(v)}">{v:.0f}B</td>' for v in row)
        heat += "</tr>"

    # Executive Summary
    thesis = executive_summary.get("thesis", ["",""])
    developments = executive_summary.get("developments", ["","",""])
    thesis_html = " ".join(f"<p>{t}</p>" for t in thesis[:2])
    dev_html = "".join(f"<li>{pt}</li>" for pt in developments[:3])

    # Company profile grid
    prod_html = ", ".join(profile.get("products",[])[:5])
    cust_tags = profile.get("customers_tags", profile.get("customers",[]))
    cust_dynamics = profile.get("customers_dynamics","")
    cust_html = ", ".join(cust_tags[:4])
    profile_html = (
        f'<div class="profile-grid">'
        f'<div class="pg-card"><div class="pg-icon">🏢</div><div class="pg-label">Business</div>'
        f'<div class="pg-val">{profile.get("business","")}</div></div>'
        f'<div class="pg-card"><div class="pg-icon">📦</div><div class="pg-label">Core Products</div>'
        f'<div class="pg-val">{prod_html}</div></div>'
        f'<div class="pg-card"><div class="pg-icon">👥</div><div class="pg-label">Key Customers</div>'
        f'<div class="pg-val">{cust_html}</div>'
        f'<div class="cust-dynamics">{cust_dynamics}</div></div>'
        f'<div class="pg-card"><div class="pg-icon">💰</div><div class="pg-label">Business Model</div>'
        f'<div class="pg-val">{profile.get("model","")}</div></div>'
        f'</div>'
    )

    # Financial 4-signal horizontal
    fin4_keys = ["Free Cash Flow","ROE","Gross Margin","Net Cash"]
    fin4_html = ""; extra_rows = ""
    fin4_count = 0
    for metric,info in financials.items():
        val=info.get("value","—"); sig=info.get("signal","")
        col={"🟢":"#22c55e","🟡":"#eab308","🔴":"#ef4444","🚩":"#ef4444"}.get(sig[:1] if sig else "","#666")
        dot="🟢" if col=="#22c55e" else ("🟡" if col=="#eab308" else "🔴")
        is_core = any(k.lower() in metric.lower() for k in fin4_keys) and fin4_count < 4
        if is_core:
            fin4_count += 1
            fin4_html += (
                f'<div class="fin4-card">'
                f'<div class="f4-name">{metric}{_tip(metric)}</div>'
                f'<div class="f4-val">{val}</div>'
                f'<div class="f4-sig" style="color:{col}">{dot} {sig.lstrip("🟢🟡🔴🚩").strip()}</div>'
                f'</div>'
            )
        else:
            row=f"<tr><td>{metric}{_tip(metric)}</td><td class='num'>{val}</td><td><span style='color:{col};font-size:12px'>{sig}</span></td></tr>"
            extra_rows += row

    # Scorecard
    sc_order = [
        ("Financial Health","financial_health","What it means for you: Does this company have a financial future?"),
        ("Earnings Quality","earnings_quality","What it means for you: Can you trust the numbers?"),
        ("Competitive Moat","competitive_moat","What it means for you: Will this business still exist in 5 years?"),
        ("Valuation vs DCF","valuation","What it means for you: Are you overpaying right now?"),
        ("Market Sentiment","market_sentiment","What it means for you: How excited is everyone else already?"),
        ("Policy & Macro Risk","policy_risk","What it means for you: Is there an external force that could blindside it?"),
    ]
    sc_rows = ""
    for label,key,meaning in sc_order:
        item=scorecard.get(key,{}); sig=item.get("signal","yellow")
        note=item.get("note",""); col=SC_COLOR.get(sig,"#888"); lbl=SC_LABEL.get(sig,sig)
        plain=SC_PLAIN.get(key,{}).get(sig,"")
        sc_rows += (
            f'<div class="sc-row">'
            f'<div class="sc-left">'
            f'<div class="sc-top"><span class="sc-dot" style="background:{col}"></span>'
            f'<span class="sc-label">{label}</span>'
            f'<span class="sc-badge" style="color:{col};border-color:{col}">{lbl}</span></div>'
            f'<div class="sc-meaning">{meaning}</div>'
            f'<div class="sc-plain">{plain}</div>'
            f'<div class="sc-note">{note}</div>'
            f'</div></div>'
        )
    sc_footer = (
        f'<div class="sc-final" style="border-color:{overall_col};background:{overall_col}12">'
        f'<div class="sf-row">'
        f'<span class="sf-label">Overall Valuation</span>'
        f'<span class="sf-verdict" style="color:{overall_col}">{overall_lbl}</span>'
        f'</div>'
        f'<div class="sf-note">Synthesized from 6 dimensions — not a buy/sell signal</div>'
        f'</div>'
    )

    # Investment Thesis card — invalidation triggers + uncertainty
    trig_html = "".join(f"<li>{t}</li>" for t in triggers)
    risk_disp = f"{risk_score}/10" if risk_score else "—"

    # Participation options (rebuilt for yellow decision card)
    part_opts = _participation_options(val_state)
    part_html = "".join(f"<li>{o}</li>" for o in part_opts)

    # Risk score HTML block
    risk_html = ""
    if risk_score:
        risk_html = (
            f'<div class="risk-row">'
            f'<span class="risk-label">Risk Score</span>'
            f'<span class="risk-val">{risk_score}/10</span>'
            f'<span class="risk-note">means high uncertainty, not "will drop {risk_score*10}%"</span>'
            f'</div>'
        )

    # Price anchor
    cur_px  = price_anchor.get("current_price", current_price or "—")
    fair_px = price_anchor.get("fair_value","—")
    gap_disp = price_anchor.get("gap_pct","—")
    gap_note = price_anchor.get("gap_label","")
    max_dd = hist_dd.get("max","—"); avg_dd = hist_dd.get("avg","—")
    try: gn = float(str(gap_disp).replace("%","").replace("+",""))
    except: gn = 0
    gap_col = "#ef4444" if gn > 0 else "#22c55e"

    # Market temp
    temp_cfg = [
        ("Fear & Greed (Market-wide)","fear_greed","score","level","macro"),
        ("Valuation Stretch (Forward P/E vs 5-Yr Median)","pe_vs_history","value","level","stock"),
        ("Wall Street Crowding Risk (Consensus Allocation)","analyst_expectations","value","level","stock"),
        ("Systemic Market Volatility (Beta Coefficient)","beta","value","level","stock"),
    ]
    macro_rows=""; stock_rows=""
    for label,key,vk,lk,grp in temp_cfg:
        item=market_temp.get(key,{}); val=item.get(vk,None); lvl=item.get(lk,"normal")
        col=_tc(lvl); pct=item.get("pct",0)
        if val is None:
            row=f'<div class="temp-item temp-miss"><span class="temp-label">{label}</span><span class="temp-na">Data unavailable</span></div>'
        else:
            row=(f'<div class="temp-item"><span class="temp-label">{label}</span>'
                 f'<span class="temp-val" style="color:{col}">{val}</span>'
                 f'<div class="temp-bar-wrap"><div class="temp-bar" style="width:{pct}%;background:{col}"></div></div></div>')
        if grp=="macro": macro_rows+=row
        else: stock_rows+=row

    dcf_limit = d.get("dcf_limitation","DCF assumes the company eventually matures and growth slows. For platform companies, this assumption may be too conservative.")
    why_right = conclusion.get("why_this_verdict","")
    why_wrong  = conclusion.get("model_blind_spots","")

    cur_display = f"${current_price}" if current_price else "—"

    # Pre-compute Bull / Bear HTML fragments
    bull_pts = "".join(f"<li>{p}</li>" for p in bull_case.get("points",[]))
    bear_pts = "".join(f"<li>{p}</li>" for p in bear_case.get("points",[]))
    bull_tp = bull_case.get("target_price","—")
    bear_tp = bear_case.get("target_price","—")
    bull_tp_disp = f"${bull_tp:.2f}" if isinstance(bull_tp,(int,float)) else str(bull_tp)
    bear_tp_disp = f"${bear_tp:.2f}" if isinstance(bear_tp,(int,float)) else str(bear_tp)

    # ── Investment Thesis card — 3-layer funnel content ──
    pe_detail = d.get("pe_detail", {})
    pe_cur    = pe_detail.get("current") or None

    def _num(x):
        try: return float(x)
        except (TypeError, ValueError): return None
    def _rel(p, ref):
        if p is None or ref is None or ref <= 0: return None
        return (p - ref) / ref * 100

    price_num = _num(cur_px)
    fair_ref  = _num(fair_px)
    bull_ref  = bull_tp if isinstance(bull_tp,(int,float)) else _num(bull_px)

    # Layer 1 — Valuation Anchor (pure fact, no second-person, no interpretation)
    _anchor_parts = []
    if price_num is not None:
        _seg  = f"At ${price_num:,.2f}, the stock trades"
        _rels = []
        _pb = _rel(price_num, bull_ref)
        if _pb is not None:
            _rels.append(f"{abs(_pb):.0f}% {'above' if _pb >= 0 else 'below'} the Bull Case target (${bull_ref:,.2f})")
        _pf = _rel(price_num, fair_ref)
        if _pf is not None:
            _rels.append(f"{abs(_pf):.0f}% {'above' if _pf >= 0 else 'below'} blended fair value (${fair_ref:,.2f})")
        _seg += (" " + " and ".join(_rels) + ".") if _rels else " at the levels shown above."
        _anchor_parts.append(_seg)
    if pe_cur and valuation_pct is not None:
        _anchor_parts.append(f"The current PE ({pe_cur:.1f}x) sits at the {valuation_pct}th percentile of the 5-year range.")
    elif valuation_pct is not None:
        _anchor_parts.append(f"Valuation sits at the {valuation_pct}th percentile of the 5-year range.")
    anchor_sentence = " ".join(_anchor_parts) if _anchor_parts else (gap_note or "Valuation anchor data unavailable.")

    # Layer 2 — Scenario Premise (one key driver each)
    bull_premise = (bull_case.get("points") or ["Sustained execution against the optimistic growth path."])[0]
    bear_premise = (bear_case.get("points") or ["Materialization of the primary downside risk."])[0]

    # Thesis Body — 3 paragraphs (institutional, no second-person; integrates basis + blind spots)
    _pe_med  = pe_detail.get("median_5yr")
    _pe_prem = pe_detail.get("premium_to_median")
    if pe_cur and _pe_med:
        tv_p1 = f"The current PE of {pe_cur:.1f}x sits at the {valuation_pct}th percentile of the past five years"
        tv_p1 += (f", {abs(_pe_prem):.0f}% {'above' if (_pe_prem or 0) >= 0 else 'below'} the 5-year median of {_pe_med:.1f}x."
                  if _pe_prem is not None else ".")
    else:
        tv_p1 = "Historical valuation-percentile data is unavailable for this name, so positioning versus the multi-year range cannot be quantified."

    tv_p2 = why_right or "The valuation conclusion rests on the gap between the current price and the modelled scenario range."

    _blend_method = d.get("blend_method", "")
    _dcf_meta     = d.get("dcf_meta", {})
    _wacc_v       = _dcf_meta.get("wacc")
    _growth_src   = _dcf_meta.get("base_growth_source")
    tv_p3 = "Fair value blends " + (_blend_method if _blend_method else "the DCF and peer-comparable methods")
    if _wacc_v:     tv_p3 += f", with cash flows discounted at a CAPM-derived WACC of {_wacc_v*100:.1f}%"
    if _growth_src: tv_p3 += f" and growth anchored to {_growth_src}"
    tv_p3 += "."
    if why_wrong:   tv_p3 += f" {why_wrong}"

    CSS = """
:root[data-theme="dark"]{
  --bg:#08080f;--surface:#111118;--surface2:#1a1a24;--border:#252535;
  --text:#e4e4f0;--muted:#7070a0;--accent:#6366f1;--heading:#fff;
  --shadow:0 2px 16px rgba(0,0,0,.5);
}
:root[data-theme="light"]{
  --bg:#f5f3ef;--surface:#fff;--surface2:#f0ede8;--border:#e0ddd8;
  --text:#1a1a2e;--muted:#6b6b80;--accent:#0f2042;--heading:#0f2042;
  --shadow:0 1px 6px rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Outfit',sans-serif;font-size:14px;line-height:1.7;transition:background .3s,color .3s}

/* Header */
.hdr{padding:40px 44px 36px;border-bottom:1px solid var(--border);position:relative;overflow:hidden}
[data-theme="dark"] .hdr{background:linear-gradient(140deg,#0c0c1e 0%,#130e28 60%,#0c0c1e 100%)}
[data-theme="light"] .hdr{background:linear-gradient(140deg,#0f2042 0%,#1e3a7e 100%)}
.hdr::before{content:'';position:absolute;top:-100px;right:-100px;width:400px;height:400px;background:radial-gradient(circle,rgba(99,102,241,.12) 0%,transparent 65%);pointer-events:none}
.hdr-eye{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.18em;color:rgba(255,255,255,.4);text-transform:uppercase;margin-bottom:10px}
.hdr-name{font-family:'DM Serif Display',serif;font-size:38px;color:#fff;line-height:1.05;margin-bottom:8px}
.hdr-price{font-family:'DM Mono',monospace;font-size:20px;color:rgba(255,255,255,.85);margin-bottom:6px}
.hdr-sub{font-family:'DM Mono',monospace;font-size:11px;color:rgba(255,255,255,.38)}
.hdr-chips{display:flex;gap:10px;margin-top:22px;flex-wrap:wrap}
.chip{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:20px;padding:4px 14px;font-family:'DM Mono',monospace;font-size:11px;color:rgba(255,255,255,.5)}
.chip strong{color:#fff}

/* Layout */
.wrap{max-width:880px;margin:0 auto;padding:32px 28px 80px}
.sec-title{font-family:'DM Serif Display',serif;font-size:20px;color:var(--heading);margin:32px 0 12px;display:flex;align-items:center;gap:10px}
.sec-caption{font-size:13px;color:var(--muted);margin:-6px 0 14px;line-height:1.55;font-style:italic}
.ledger{margin:4px 0 0}
.ledger>summary{font-size:10px}
.sec-title::after{content:'';flex:1;height:1px;background:var(--border)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:22px;margin-bottom:14px;box-shadow:var(--shadow)}
.card-lbl{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--border)}

/* Executive Summary */
.exec-thesis{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.18);border-radius:10px;padding:18px 22px;margin-bottom:12px}
[data-theme="light"] .exec-thesis{background:rgba(99,102,241,.06);border-color:rgba(99,102,241,.14)}
.et-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin-bottom:10px}
.et-body p{margin-bottom:6px;font-size:14px;line-height:1.6;color:var(--text)}
.exec-devs{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 22px;margin-bottom:14px}
.ed-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.exec-devs ul{padding-left:18px}
.exec-devs li{margin-bottom:6px;font-size:13px;line-height:1.55;color:var(--text))}

/* Company profile */
.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.pg-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px}
.pg-icon{font-size:18px;margin-bottom:6px}
.pg-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.pg-val{font-size:13px;color:var(--text);line-height:1.5}
.cust-dynamics{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5;font-style:italic}
.tag{display:inline-block;background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:2px 8px;font-size:12px;margin:2px 2px 2px 0;color:var(--text)}

/* Financial 4-signal */
.fin4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.fin4-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 12px;text-align:center}
.f4-name{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.f4-val{font-family:'DM Serif Display',serif;font-size:20px;color:var(--text);margin-bottom:4px}
.f4-sig{font-size:11px;font-family:'DM Mono',monospace}
table{width:100%;border-collapse:collapse;margin-top:12px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);font-size:13px}
th{color:var(--muted);font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.07em}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--surface2)}
.num{font-family:'DM Mono',monospace}
.tip{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;background:var(--surface2);border:1px solid var(--border);font-size:9px;color:var(--muted);cursor:help;margin-left:4px;vertical-align:middle}

/* Scorecard */
.sc-row{padding:14px 0;border-bottom:1px solid var(--border)}
.sc-row:last-child{border-bottom:none}
.sc-top{display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap}
.sc-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.sc-label{font-size:13px;font-weight:600;color:var(--text)}
.sc-badge{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.06em;padding:2px 8px;border:1px solid;border-radius:10px}
.sc-meaning{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.04em;color:var(--accent);margin-bottom:3px;margin-top:2px}
.sc-plain{font-size:13px;color:var(--text);font-style:italic;margin-bottom:2px}
.sc-note{font-size:12px;color:var(--muted)}
.sc-final{border:2px solid;border-radius:10px;padding:14px 18px;margin-top:16px}
.sf-row{display:flex;align-items:center;gap:14px;margin-bottom:4px}
.sf-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.sf-verdict{font-family:'DM Serif Display',serif;font-size:20px;font-weight:700}
.sf-note{font-size:11px;color:var(--muted);font-family:'DM Mono',monospace}

/* Bull / Bear Dual-Core */
.bb-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.bb-card{border-radius:12px;padding:20px;border:1px solid var(--border)}
.bb-bull{background:rgba(34,197,94,.06);border-color:rgba(34,197,94,.2)}
.bb-bear{background:rgba(239,68,68,.06);border-color:rgba(239,68,68,.2)}
.bb-head{font-family:'DM Mono',monospace;font-size:12px;font-weight:600;letter-spacing:.06em;margin-bottom:12px}
.bb-bull .bb-head{color:#22c55e}
.bb-bear .bb-head{color:#ef4444}
.bb-list{padding-left:16px}
.bb-list li{margin-bottom:6px;font-size:13px;color:var(--text);line-height:1.55}
.bb-stitch{margin-bottom:0}

/* Decision card tight coupling after Bull/Bear */
.dec-card-tight{border:2px solid;border-radius:0 0 14px 14px;padding:24px;margin-bottom:14px;margin-top:-2px;border-top:none}
.dec-card{border:2px solid;border-radius:14px;padding:24px;margin-bottom:14px}
.anchor-para{font-size:14px;color:var(--text);line-height:1.65;margin-bottom:16px;padding:12px 16px;background:var(--surface2);border-radius:8px;border-left:3px solid var(--accent)}
.risk-para{font-size:14px;color:var(--text);line-height:1.65;margin-bottom:16px;padding:12px 16px;background:rgba(239,68,68,.06);border-radius:8px;border-left:3px solid #ef4444}
.dec-stitch{margin-top:16px}
.dec-divider{height:2px;border-radius:1px;margin-bottom:20px;opacity:.3}
.val-pill{display:inline-block;padding:6px 16px;border-radius:20px;font-family:'DM Mono',monospace;font-size:12px;font-weight:600;letter-spacing:.06em;margin-bottom:14px}
.val-text{font-size:15px;color:var(--text);line-height:1.6;margin-bottom:16px;padding:12px 16px;background:var(--surface2);border-radius:8px;border-left:3px solid}
.honesty{background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.2);border-radius:8px;padding:14px 16px;margin-bottom:16px}
.honesty-title{color:#ef4444;font-size:12px;font-weight:600;font-family:'DM Mono',monospace;letter-spacing:.04em;margin-bottom:6px}
.honesty p{font-size:13px;color:var(--muted);line-height:1.65}
.part-title{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px}
.part-note{font-size:11px;color:var(--muted);font-style:italic}
.part-list{padding-left:16px;margin-bottom:16px}
.part-list li{margin-bottom:6px;font-size:13px;color:var(--text)}
.trig-list{padding-left:16px;margin-bottom:16px}
.trig-list li{margin-bottom:6px;font-size:13px;color:var(--muted)}
.risk-row{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--surface2);border-radius:8px;flex-wrap:wrap}
.risk-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.risk-val{font-family:'DM Serif Display',serif;font-size:22px;color:var(--text)}
.risk-note{font-size:12px;color:var(--muted);font-style:italic}

/* Investment Thesis card — 3-layer funnel */
.val-anchor{font-size:16px;line-height:1.6;color:var(--text);font-weight:500;padding-bottom:16px;margin-bottom:16px;border-bottom:1px solid var(--border)}
.premise-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.premise-bull,.premise-bear{border-radius:10px;padding:14px 16px;border:1px solid var(--border)}
.premise-bull{background:rgba(34,197,94,.06);border-color:rgba(34,197,94,.2)}
.premise-bear{background:rgba(239,68,68,.06);border-color:rgba(239,68,68,.2)}
.pm-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}
.premise-bull .pm-label{color:#22c55e}
.premise-bear .pm-label{color:#ef4444}
.premise-bull p,.premise-bear p{font-size:13px;color:var(--text);line-height:1.55;margin:0}
/* Investment Thesis card — clean analysis flow (no nested cards / inner borders) */
.tv-anchor{font-size:17px;font-weight:600;line-height:1.6;color:var(--text);margin-bottom:18px}
.tv-body{margin-bottom:18px}
.tv-body p{font-size:14px;line-height:1.7;color:var(--text);margin-bottom:16px}
.tv-body p:last-child{margin-bottom:0}
.tv-alert{background:rgba(234,179,8,.10);border-radius:8px;padding:12px 16px;margin-bottom:18px;font-size:13px;line-height:1.65;color:var(--text)}
.tv-alert strong{color:#a16207}
[data-theme="dark"] .tv-alert strong{color:#eab308}
.tv-details{border:none;border-radius:0;background:none;overflow:visible;margin:0 0 16px}
.tv-details>summary{padding:6px 0;background:none;color:var(--accent);text-transform:none;letter-spacing:.02em;font-size:12px}
.tv-details>summary:hover{color:var(--heading)}
.tv-details .det-inner{padding:8px 0 0}
.tv-details .trig-list{padding-left:18px;margin:0}
.tv-details .trig-list li{margin-bottom:6px;font-size:13px;line-height:1.6;color:var(--text)}
.tv-footer{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:11px 16px;background:var(--surface2);border-radius:8px}
.tv-risk{font-family:'DM Mono',monospace;font-size:13px;font-weight:600;color:#a16207;white-space:nowrap}
[data-theme="dark"] .tv-risk{color:#eab308}
.tv-disc{font-size:12px;color:var(--muted);font-style:italic}

/* Scenario plots moved into Investment Thesis (collapsible charts) */
.thesis-plots{margin-top:14px;margin-bottom:14px}
.tp-card{margin-bottom:14px}
.tp-card:last-child{margin-bottom:0}
.tp-body{padding:18px}
.thesis-analysis{border-top:1px dashed var(--border);margin-top:6px;padding-top:14px;margin-bottom:4px}
.thesis-analysis .expl-row{margin-bottom:14px}
.thesis-analysis .expl-row:last-child{margin-bottom:0}

/* Price anchor */
.anchor-row{display:flex;align-items:center;gap:0;margin-bottom:14px}
.anc-block{flex:1;text-align:center;padding:14px 10px}
.anc-lbl{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.anc-val{font-family:'DM Serif Display',serif;font-size:28px;color:var(--text)}
.anc-arrow{font-size:22px;color:var(--muted);padding:0 8px}
.anc-gap{font-family:'DM Mono',monospace;font-size:26px;font-weight:700}
.anc-note{font-size:13px;color:var(--muted);font-style:italic;margin-bottom:12px;line-height:1.55}
.dd-bar{background:var(--surface2);border-radius:8px;padding:10px 14px;font-family:'DM Mono',monospace;font-size:12px;color:var(--muted);display:flex;gap:24px;flex-wrap:wrap}
.dd-item strong{color:var(--text)}

/* Valuation model */
.chart-wrap{position:relative;height:200px;margin-top:8px}
.sent-check{border-radius:8px;padding:12px 16px;margin-top:12px;font-size:13px;line-height:1.6;display:flex;gap:10px}
.sent-check.hot{background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.2)}
.sent-check.cool{background:rgba(34,197,94,.07);border:1px solid rgba(34,197,94,.2)}
.sent-check.mid{background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2)}
.sc-icon{font-size:18px;flex-shrink:0}
.dcf-note{margin-top:12px;padding:8px 14px;background:var(--surface2);border-radius:6px;font-size:12px;color:var(--muted);font-style:italic}

/* Sensitivity */
.heat-wrap{overflow-x:auto}
.heat-wrap table th{color:var(--muted);font-size:11px;padding:6px 8px;text-align:center;background:var(--surface2);font-family:'DM Mono',monospace;border-bottom:none}
.heat-wrap table td{font-family:'DM Mono',monospace;font-size:11px;padding:6px 8px;text-align:center;border:1px solid var(--bg)}
.heat-legend{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:11px;color:var(--muted);font-family:'DM Mono',monospace}
.heat-grad{flex:1;height:5px;border-radius:3px;background:linear-gradient(to right,#ef4444,#eab308,#22c55e)}

/* Emotion meter */
.em-wrap{margin:4px 0 14px}
.em-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.em-verdict{font-family:'DM Mono',monospace;font-size:12px;font-weight:600}
.em-pct{font-family:'DM Mono',monospace;font-size:11px;color:var(--muted)}
.em-track{height:8px;background:linear-gradient(to right,#22c55e 0%,#eab308 50%,#ef4444 100%);border-radius:4px;position:relative;margin-bottom:10px}
.em-needle{position:absolute;top:50%;transform:translate(-50%,-50%);width:3px;height:20px;background:#fff;border-radius:2px;box-shadow:0 0 8px rgba(0,0,0,.6)}
.em-desc{font-size:12px;color:var(--muted);font-style:italic}

/* Market temp */
.sent-warn{font-size:12px;color:var(--muted);font-style:italic;padding:8px 12px;background:var(--surface2);border-radius:6px;margin-bottom:12px;border-left:3px solid #eab308}
.sent-sec{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:12px 0 6px}
.temp-item{display:grid;grid-template-columns:180px 110px 1fr;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--border)}
.temp-item:last-child,.temp-miss:last-child{border-bottom:none}
.temp-miss{display:grid;grid-template-columns:180px 1fr;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--border)}
.temp-label{font-size:13px;color:var(--text)}
.temp-val{font-family:'DM Mono',monospace;font-size:12px;font-weight:600}
.temp-na{font-size:12px;color:var(--muted);font-style:italic}
.temp-bar-wrap{height:4px;background:var(--surface2);border-radius:2px;overflow:hidden}
.temp-bar{height:100%;border-radius:2px}

/* Analyst explanation */
.expl-row{margin-bottom:16px}
.expl-lbl{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.expl-val{font-size:14px;color:var(--text);line-height:1.65}

/* Details/summary */
details{border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:14px}
summary{padding:13px 18px;cursor:pointer;font-family:'DM Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);background:var(--surface2);list-style:none;display:flex;justify-content:space-between;align-items:center;user-select:none}
summary:hover{color:var(--text)}
summary::after{content:'▸';transition:transform .2s}
details[open] summary::after{content:'▾'}
.det-inner{padding:18px 20px}
.appx-merge{border-top:1px dashed var(--border);margin-top:20px;padding-top:18px}

.app-divider{margin:18px 0;border-top:1px dashed var(--border)}
.disclaimer{margin-top:48px;padding:14px 18px;background:var(--surface);border:1px solid var(--border);border-radius:8px;font-size:11px;color:var(--muted);line-height:1.75;font-family:'DM Mono',monospace}
.disclaimer strong{display:block;margin-bottom:10px;font-size:11px;color:var(--heading);letter-spacing:.04em;text-transform:uppercase}
.disclaimer p{margin:0 0 10px}
.disclaimer p:last-child{margin-bottom:0}
.disclaimer code{font-family:'DM Mono',monospace;font-size:10px;background:var(--surface2);padding:1px 5px;border-radius:4px}

@media(max-width:640px){
  .fin4{grid-template-columns:1fr 1fr}
  .profile-grid{grid-template-columns:1fr}
  .premise-grid{grid-template-columns:1fr}
  .tv-anchor{font-size:15px}
  .tv-body p{font-size:13px}
  .anchor-row{flex-direction:column}
  .hdr-name{font-size:28px}
  .wrap{padding:24px 16px 60px}
  .hdr{padding:28px 20px 24px}
  .temp-item{grid-template-columns:1fr 1fr}
}
@media print{
  [data-theme="dark"]{--bg:#fff;--surface:#fff;--surface2:#f5f5f5;--border:#ddd;--text:#111;--muted:#555;--accent:#0f2042;--heading:#0f2042}
}
"""

    JS = """
var _charts={};
function renderCharts(){
  var dark=document.documentElement.getAttribute('data-theme')==='dark';
  var gc=dark?'rgba(255,255,255,.06)':'rgba(0,0,0,.06)';
  var lc=dark?'#7070a0':'#6b6b80';
  var bg2=dark?'#1a1a24':'#e8e6e0';
  if(_charts.dcf)_charts.dcf.destroy();
  var dcfEl=document.getElementById('dcf-chart');
  if(dcfEl){
    _charts.dcf=new Chart(dcfEl,{
      type:'bar',
      data:{labels:DCFLABELS,datasets:[{data:DCFVALUES,backgroundColor:['#22c55e','#6366f1','#f97316'],borderRadius:7,borderSkipped:false}]},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return ' $'+ctx.parsed.y.toFixed(0)+'B | $'+DCFPRICES[ctx.dataIndex]+'/sh';}}}},
        scales:{x:{grid:{color:gc},ticks:{color:lc,font:{family:'DM Mono',size:11}}},
                y:{grid:{color:gc},ticks:{color:lc,font:{family:'DM Mono',size:11},callback:function(v){return v+'B';}}}}}
    });
  }
}
document.addEventListener('DOMContentLoaded',renderCharts);
"""
    JS=(JS.replace("DCFLABELS",dcf_labels)
          .replace("DCFVALUES",dcf_values)
          .replace("DCFPRICES",dcf_prices))

    return (
        "<!DOCTYPE html>\n<html lang='en' data-theme='light'>\n<head>\n"
        "<meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>\n"
        f"<title>{company_name} ({ticker})</title>\n"
        "<link href='https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap' rel='stylesheet'>\n"
        "<script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'></script>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"

        # === LAYER 1: HEADER ===
        f"<div class='hdr'>"
        f"<div class='hdr-eye'>{ticker} · Stock Analysis</div>"
        f"<div class='hdr-name'>{company_name}</div>"
        f"<div class='hdr-price'>{cur_display}</div>"
        f"<div class='hdr-sub'>Data: yfinance · DCF model · {date}</div>"
        f"<div class='hdr-chips'>"
        f"<div class='chip'><strong>{ticker}</strong></div>"
        f"<div class='chip'>Generated <strong>{date}</strong></div>"
        f"<div class='chip'>company-analyst <strong>v5.4</strong></div>"
        f"</div></div>\n"

        "<div class='wrap'>\n"

        # === LAYER 2: EXECUTIVE SUMMARY + PROFILE ===
        f"<div class='sec-title'>Executive Summary</div>\n"
        f"<div class='exec-thesis'>"
        f"<div class='et-label'>Core Thesis</div>"
        f"<div class='et-body'>{thesis_html}</div></div>\n"
        f"<div class='exec-devs'><div class='ed-label'>Latest Developments</div><ul>{dev_html}</ul></div>\n"

        f"<div class='sec-title'>Company Profile</div>\n"
        f"<div class='card'>{profile_html}</div>\n"
        f"<div class='fin4'>{fin4_html}</div>\n"

        # === LAYER 3: INVESTMENT THESIS (anchor + scenarios + plots + decision, one section) ===
        f"<div class='sec-title'>Investment Thesis</div>\n"
        f"<div class='card'>"
        f"<div class='anchor-row'>"
        f"<div class='anc-block'><div class='anc-lbl'>Current Price</div><div class='anc-val'>${cur_px}</div></div>"
        f"<div class='anc-arrow'>→</div>"
        f"<div class='anc-block'><div class='anc-lbl'>Base DCF Fair Value</div><div class='anc-val'>${fair_px}</div></div>"
        f"<div class='anc-arrow'>·</div>"
        f"<div class='anc-block'><div class='anc-lbl'>Gap</div><div class='anc-gap' style='color:{gap_col}'>{gap_disp}</div></div>"
        f"</div>"
        f"<div class='anc-note'>{gap_note}</div>"
        f"<div class='dd-bar'>📉 Historical drawdowns: <span><strong>Max</strong> {max_dd}</span> <span><strong>Avg</strong> {avg_dd}</span></div>"
        f"</div>\n"

        # Bull / Bear scenarios (flows directly under the anchor — no separate heading)
        f"<div class='bb-grid'>"
        f"<div class='bb-card bb-bull'>"
        f"<div class='bb-head'>🎯 Bull Case ｜ Target Price: {bull_tp_disp}</div>"
        f"<ul class='bb-list'>{bull_pts}</ul></div>"
        f"<div class='bb-card bb-bear'>"
        f"<div class='bb-head'>🚨 Bear Case ｜ Target Price: {bear_tp_disp}</div>"
        f"<ul class='bb-list'>{bear_pts}</ul></div>"
        f"</div>"

        # Scenario plots — moved up from the appendix, collapsible (open by default)
        f"<div class='thesis-plots'>"
        f"<details class='tp-card' open ontoggle='if(this.open)renderCharts()'>"
        f"<summary>DCF — Three Scenarios (Equity Value $B)</summary>"
        f"<div class='tp-body'><div class='chart-wrap'><canvas id='dcf-chart'></canvas></div>"
        f"<div class='dcf-note'>⚠ DCF limitation: {dcf_limit}</div></div></details>"
        f"<details class='tp-card' open>"
        f"<summary>Sensitivity — WACC × Terminal Growth ($B)</summary>"
        f"<div class='tp-body'><div class='heat-wrap'><table>{heat}</table></div>"
        f"<div class='heat-legend'><span>Low</span><div class='heat-grad'></div><span>High</span></div></div></details>"
        f"</div>"

        # === LAYER 4: YELLOW DECISION CARD — strict 4-block Investment Thesis ===
        f"<div class='dec-card-tight' style='border-color:{val_color};border-top:2px solid {val_color};border-radius:14px;margin-top:0'>"
        f"<div class='val-pill' style='color:{val_color};border:1.5px solid {val_color};background:{val_color}14'>Valuation Assessment</div>"
        # Block 1 — Market Psychology & Valuation Assessment (qualitative paragraph, no formula)
        f"<div class='part-title'>👁️ Market Psychology &amp; Valuation Assessment</div>"
        f"<div class='anchor-para'>{valuation_anchor}</div>"
        # Block 2 — Single concrete fundamental risk (specific, no placeholders)
        f"<div class='part-title'>🚨 Key Structural Risk</div>"
        f"<div class='risk-para'>{key_risk}</div>"
        # Block 3 — Dynamic invalidation triggers (exactly 3: Price / Fundamental / Macro)
        f"<div class='part-title'>🎯 What would change this analysis</div>"
        f"<ul class='trig-list'>{trig_html}</ul>"
        # Block 4 — Tool boundary disclaimer (fixed institutional wording)
        f"<div class='honesty'><div class='honesty-title'>🛡️ Risk &amp; Model Boundaries</div>"
        f"<p>Our quantitative framework measures fundamental intrinsic value, not short-term market sentiment or tomorrow's price direction. "
        f"Expensive stocks can remain overvalued due to momentum; cheap stocks can stay depressed. "
        f"Use this analysis as an execution map, not a crystal ball.</p></div>"
        # Retained verbatim — Uncertainty Score component
        f"{risk_html}"
        f"</div>\n"

        # === LAYER 5: RISK ASSESSMENT & TELEMETRY (between Investment Thesis and Scorecard) ===
        f"<div class='sec-title'>Risk Assessment</div>\n"
        f"<div class='sec-caption'>Quantitative stress-testing of market crowding, valuation stretch, and capital volatility.</div>\n"
        f"<div class='card'>"
        f"<div class='em-wrap'>"
        f"<div class='em-top'><span class='em-verdict' style='color:{em_color}'>{em_label}</span><span class='em-pct'>P/E historical percentile</span></div>"
        f"<div class='em-track'><div class='em-needle' style='left:{meter_pct}%'></div></div>"
        f"<div class='em-desc'>{em_desc}</div>"
        f"</div>"
        f"<div class='sent-sec'>Macro — Whole Market</div>{macro_rows}"
        f"<div class='sent-sec'>This Stock</div>{stock_rows}"
        f"<div class='app-divider'></div>"
        # Raw financial ledger isolated in a nested toggle — default collapsed
        f"<details class='ledger'><summary>Appendix: Financial Integrity Check</summary>"
        f"<div class='det-inner'>"
        f"<table><thead><tr><th>Metric</th><th>Value</th><th>Signal</th></tr></thead>"
        f"<tbody>{extra_rows}</tbody></table>"
        f"</div></details>"
        f"</div>\n"

        f"<div class='sec-title'>Signal Scorecard</div>\n"
        f"<div class='card'>{sc_rows}{sc_footer}</div>\n"

        # === DISCLAIMER ===
        f"<div class='disclaimer'>"
        f"<strong>Important Financial Disclaimer &amp; Model Limitations</strong>"
        f"<p>This automated report is generated strictly for informational and educational research purposes by the "
        f"<code>company-analyst</code> open-source skill. It does not constitute, and shall not be construed as, "
        f"professional investment advice, financial planning, or a solicitation to buy or sell any financial instrument.</p>"
        f"<p>All quantitative outputs—including the Blended Fair Value, dynamic DCF models, and PE percentiles—are "
        f"mathematical inferences back-solved from publicly available market data (yfinance). Financial models are "
        f"highly sensitive to baseline growth assumptions, meaning macroeconomic shocks or operational volatility can "
        f"render any intrinsic valuation invalid. Users must perform independent due diligence and verify all inputs "
        f"prior to allocating capital; the authors and contributors assume absolutely no liability for any financial "
        f"losses incurred from the utilization of this repository.</p>"
        f"</div>\n"

        "</div>\n"
        f"<script>{JS}</script>\n"
        "</body></html>"
    )


if __name__ == "__main__":
    sample = {
        "ticker":"NVDA","company_name":"Nvidia Corporation","date":"2026-05-23",
        "current_price":215.33,
        "margins":{"gross_margin":74.1,"fcf_margin":29.1,"net_margin":63.0},
        "valuation_percentile":91,
        "historical_drawdowns":{"max":"-66%","avg":"-32%"},
        "company_profile":{
            "business":"Nvidia designs the chips that power AI computing — it does not manufacture them (TSMC does). Its CUDA software ecosystem, built over 18 years, locks customers into its platform.",
            "products":["H200/B200 Blackwell GPUs","CUDA Software Platform","NVLink Networking"],
            "customers_tags":["Microsoft Azure","Google Cloud","Amazon AWS","Meta"],
            "customers_dynamics":"Highly reliant on hyperscale cloud giants whose shifting CapEx budgets dictate revenue growth.",
            "model":"Commercial Essence: Sell GPU hardware + software ecosystem. Data Center now accounts for 91% of revenue. Customers are locked in by software, not just hardware specs.",
        },
        "executive_summary":{
            "thesis":[
                "Nvidia designs the dominant AI compute platform — CUDA's 18-year ecosystem moat makes customer switching nearly impossible.",
                "Financial profile is exceptional (74% gross margin, $68B net cash), but valuation sits above every realistic DCF scenario."
            ],
            "developments":[
                "Revenue growth deceleration signal: Data Center YoY growth moderated in latest quarter — monitor next guide for confirmation.",
                "Export control expansion risk: H20 chip restrictions to China could erase 15-20% of historical revenue.",
                "Hyperscaler CapEx cycle: MSFT/GOOGL/META cloud spend guidance is the near-term revenue bellwether."
            ],
        },
        "bull_case":{
            "target_price":143.79,
            "points":[
                "AI compute demand sustains 40%+ CAGR for 3+ years, driven by agentic AI and sovereign cloud builds.",
                "Software revenue (CUDA, AI Enterprise) mix expands, lifting blended gross margins toward 80%.",
                "Automotive and robotics chips become a material revenue line beyond Data Center."
            ],
        },
        "bear_case":{
            "target_price":50.96,
            "points":[
                "Hyperscaler CapEx peaks and normalizes, cutting Data Center revenue growth to single digits.",
                "Custom silicon (TPU, Trainium) captures 30%+ of inference workloads, eroding CUDA lock-in.",
                "Export controls expand to H20, eliminating China revenue and triggering global oversupply."
            ],
        },
        "fact_business":"Nvidia is a software-moat business in hardware clothing. CUDA's 18-year head start is the real competitive advantage — GPUs are the delivery mechanism.",
        "fact_valuation":"Current PE of 33x sits at the 91st historical percentile. The market price of $215 exceeds even the Bull DCF scenario ($144), implying the market is pricing beyond a 5-year model.",
        "fact_risk":"The largest binary risk is US export controls on advanced chips to China, which has already curtailed 15-20% of historical revenue. Further escalation or hyperscaler capex reduction would both hit the stock hard.",
        "condition_triggers":[
            "Price Trigger: A correction down to ~$130 (~10% above blended fair value), where a structural margin of safety begins to emerge",
            "Fundamental Trigger: Two consecutive quarters of missing revenue consensus, forcing a downward revision of the base-case target",
            "Macro Trigger: Monetary tightening or sector multiple compression that drops the sector-wide P/E ceiling and re-rates the stock lower",
        ],
        "risk_score":7,
        "dcf_limitation":"DCF assumes the company eventually matures and growth slows. For Nvidia, if CUDA becomes the industry standard and AI compute demand sustains for 10+ years, the terminal value could be significantly higher than the model captures.",
        "price_anchor":{
            "current_price":215.33,"fair_value":81.12,"gap_pct":"+165%",
            "gap_label":"The market has already priced in ~10 years of compounding beyond the base case. This is not a statement that the stock will fall — it means you have no cushion if anything goes wrong.",
        },
        "financials":{
            "Free Cash Flow":    {"value":"$73.7B", "signal":"🟡 Below net income"},
            "ROE":               {"value":"114%",   "signal":"🟢 Extraordinary"},
            "Gross Margin":      {"value":"74.1%",  "signal":"🟢 Software-like"},
            "Net Cash Position": {"value":"+$67.8B","signal":"🟢 Zero leverage risk"},
            "Revenue (TTM)":     {"value":"$253.5B","signal":"🟢 +85% YoY"},
            "Net Income":        {"value":"$159.6B","signal":"🟢 Highly profitable"},
            "FCF Margin":        {"value":"29.1%",  "signal":"🟢 Excellent"},
            "Interest Coverage": {"value":"~300x",  "signal":"🟢 No debt risk"},
        },
        "dcf_scenarios":[
            {"scenario":"Bull","equity_value_bn":3483,"price_per_share":143.79},
            {"scenario":"Base","equity_value_bn":1965,"price_per_share":81.12},
            {"scenario":"Bear","equity_value_bn":1234,"price_per_share":50.96},
        ],
        "sensitivity":{
            "wacc_labels":["10%","11%","12%","13%","14%"],
            "tgr_labels": ["2.0%","2.5%","3.0%","3.5%","4.0%"],
            "equity_value_bn":[[1664,1748,1845,1956,2086],[1476,1540,1611,1693,1786],[1326,1375,1430,1492,1561],[1200,1243,1290,1342,1400],[1094,1130,1170,1214,1262]],
        },
        "scorecard":{
            "financial_health":{"signal":"green", "note":"74% gross margins, $80B cash, $159B net income TTM"},
            "earnings_quality":{"signal":"yellow","note":"FCF ($73.7B) well below net income ($159.6B) — AR build warrants monitoring"},
            "competitive_moat":{"signal":"green", "note":"CUDA lock-in; no software-compatible competitor; 18-year developer ecosystem"},
            "valuation":       {"signal":"red",   "note":"$215 above Bull DCF $144 — market pricing a decade of perfect execution"},
            "market_sentiment":{"signal":"red",   "note":"58-analyst Strong Buy; Beta 2.24; prior 60%+ drawdowns show sentiment flips fast"},
            "policy_risk":     {"signal":"red",   "note":"Export controls already curtailing China revenue; further escalation is binary risk"},
        },
        "market_temp":{
            "fear_greed":          {"score":"72 — Greed",          "level":"warm","pct":72},
            "pe_vs_history":       {"value":"33x vs ~20x hist avg","level":"hot", "pct":85},
            "analyst_expectations":{"value":"Strong Buy (58 analysts)","level":"hot","pct":90},
            "beta":                {"value":"2.24",                "level":"hot", "pct":88},
        },
        "analyst_conclusion":{
            "why_this_verdict":"Three of six scorecard dimensions are red — valuation, sentiment, and policy risk. Even with a world-class business, paying 2.6x DCF fair value means any growth slowdown or sentiment shift will cause significant price damage. The Bull DCF ($144) is already 33% below the current price.",
            "model_blind_spots":"The DCF most likely underestimates Nvidia if: (1) AI compute demand sustains high growth for 10+ years; (2) CUDA evolves into an industry standard like Windows; (3) Nvidia opens major new revenue lines in robotics / physical AI. All of these are outside the assumptions baked into a 5-year DCF model.",
        },
    }
    generate_html_report(sample,"nvda_report.html")
