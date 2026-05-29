# 📊 Company Analyst

A structured equity research tool that turns any company name into a comprehensive fundamental analysis report — built for retail investors, not financial professionals.

Works as a **Claude Code skill**, a **standalone CLI tool**, and a **prompt template** for any LLM.

---

## What it does

Input a ticker → get a full research report in seconds:

- **Live financial data** pulled automatically from yfinance (no manual input)
- **Three-method valuation**: DCF + Peer Comps + PE Historical Percentile
- **Investment Thesis card**: 4-block analysis flow (market psychology, key structural risk, invalidation triggers, model boundaries)
- **Risk Assessment**: valuation-stretch / crowding / volatility gauges + isolated financial ledger
- **Honest scorecard**: 6-dimension signal grid with plain-language explanations
- **HTML report**: clean light theme, collapsible Chart.js visualizations, mobile-friendly

No BUY / SELL / HOLD labels. No specific entry prices. Just data, context, and a reference point — the decision is yours.

---

## Repository Structure

```
company-analyst/
├── analyze.py              ← Main entry point — run this
├── report_generator.py     ← HTML report renderer
├── valuation_engine.py     ← PE percentile + dynamic DCF + peer comps
├── SKILL.md                ← Claude Code skill definition
├── company-analyst.skill   ← Packaged skill file for Claude
├── requirements.txt
│
├── data/
│   ├── __init__.py
│   └── base_and_fetchers.py    ← yfinance data layer
│
├── models/
│   ├── __init__.py
│   └── all_models.py           ← DCF, WACC, FCF, sensitivity matrix
│
└── tools/
    ├── __init__.py
    └── all_tools.py            ← Tool interface layer
```

---

## Installation

```bash
# Clone the repo
git clone https://github.com/Kevin-XXX/company-analyst.git
cd company-analyst

# Install dependencies
pip install -r requirements.txt
```

`requirements.txt`:
```
yfinance
requests
numpy
python-dotenv
```

---

## CLI Usage

The fastest way to use this tool — no Claude required.

```bash
# Analyze any stock
python analyze.py AAPL
python analyze.py NVDA
python analyze.py NOK

# Hong Kong / A-share stocks
python analyze.py 0700.HK
python analyze.py 600519.SS

# Save to a specific path, skip browser open
python analyze.py AAPL --output reports/apple.html --no-browser

# Also export raw data as JSON
python analyze.py AAPL --json

# Custom risk-free rate (default: 4.3%)
python analyze.py TSLA --rf 0.045
```

**What the CLI does automatically:**
1. Fetches live price and financials from yfinance
2. Computes real 5-year PE historical percentile
3. Runs dynamic DCF anchored to analyst consensus growth
4. Runs peer comps relative valuation (vs sector peers)
5. Blends fair value: 50% DCF Base + 30% Comps + 20% DCF Bear
6. Auto-generates scorecard signals from the data
7. Renders HTML report and opens it in your browser

---

## Claude Code Usage

### Install as a skill

```bash
git clone https://github.com/Kevin-XXX/company-analyst.git ~/.claude/skills/company-analyst
```

Then in Claude Code, just say:

```
Analyze Apple for me
帮我分析英伟达
Nokia의 실적을 분석해줘
```

Claude Code will automatically run `analyze.py`, fetch live data, run the valuation models, enrich with qualitative context, and generate the HTML report.

### Trigger with slash command

```
/company-analyst Analyze NVDA
```

---

## Other LLMs (ChatGPT, Gemini, etc.)

Copy the contents of `SKILL.md` (everything below the `---` frontmatter) and paste it as a **system prompt** or **custom instruction**. Then ask about any company.

The skill will instruct the model to use web search for financial data, run the same analytical framework, and produce a structured report.

---

## Report Structure

Every report follows this layout:

| Section | Content |
|---------|---------|
| Header | Company name, live price, date, generation metadata |
| Executive Summary | Core thesis banner + 3 latest-development bullets |
| Company Profile | Business, products, customers, model + 4 core financial signal cards |
| Investment Thesis | Price → blended fair value → gap; Bull/Bear scenarios; collapsible DCF & sensitivity plots; 4-block yellow decision card |
| Risk Assessment | Valuation-stretch / crowding / volatility gauges + collapsed "Financial Integrity Check" ledger |
| Signal Scorecard | 6 dimensions with "what it means for you" + overall valuation label |
| Disclaimer | Fixed text |

The 4-block Investment Thesis card contains: **Market Psychology & Valuation Assessment**, **Key Structural Risk**, **What would change this analysis** (3 invalidation triggers), and **Risk & Model Boundaries**, plus an uncertainty score.

---

## Valuation Methodology

### 1. PE Historical Percentile
Fetches 5 years of monthly price history and reconstructs a historical PE series. Computes where the current PE sits relative to the past 5 years (0–100th percentile).

### 2. Dynamic DCF
- **Base growth rate** anchored to analyst consensus EPS/revenue estimates (falls back to historical revenue CAGR if unavailable)
- **Bull** = Base × 1.30 | **Base** = consensus | **Bear** = Base × 0.70
- **WACC** calibrated via CAPM using real Beta: `Rf + β × ERP`
- **Sensitivity matrix**: WACC range centered on CAPM result ± 2%
- **Terminal value**: Gordon Growth Model

### 3. Peer Comps
Fetches PE, EV/EBITDA, PEG, P/B, P/S for 5–6 sector peers. Computes peer medians and back-solves an implied price for the subject company at each multiple.

### 4. Blended Fair Value
```
50% DCF Base + 30% Peer Comps + 20% DCF Bear
```
When comps are unavailable: `70% DCF Base + 30% DCF Bear`

---

## Design Principles

**Data only, no advice** — the tool surfaces structured information; the user makes the call.

**No fabrication** — if data is unavailable, it is labeled as such.

**No investment recommendation** — a disclaimer is appended to every report.

**Honest about limitations** — every report includes a DCF limitation note and model blind spot section.

**Retail-first language** — every financial metric has a plain-English tooltip. The scorecard includes a "what this means for you" translation for each dimension.

---

## License

MIT — free to use, modify, and share.

---

*This tool is for research and information purposes only. Nothing it produces constitutes financial or investment advice. All figures should be independently verified.*
