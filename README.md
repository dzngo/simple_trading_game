# Options Trading Game

A lightweight Streamlit MVP for a university finance course. Students play as companies or banks, while a professor supervises the game and controls simple Market Prices.

The app intentionally avoids real option pricing, Greeks, implied volatility, exercise logic, and Black-Scholes. `Call` and `Put` are predefined classroom instruments with manually controlled prices.

## Features

- Simple login by selecting a demo user
- Company page for trade declarations with banks
- Bank page for trade declarations with companies and professor-set Market Price context
- Professor page for order/trade supervision, price configuration, reset, and Plotly analytics
- SQLite persistence
- Matching engine requiring compatible independent declarations
- Refused status when reciprocal company-bank declarations disagree
- Live dashboard sections refresh automatically every 5 seconds

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
streamlit run app.py
```

## Demo Users

- Company A
- Company B
- Bank X
- Bank Y
- Professor

## Trading Rules

A trade matches when two pending declarations have:

- the same product
- the same price
- opposite sides
- reciprocal counterparties

If a reciprocal declaration exists for the same company, bank, and product but the side or price does not match, both declarations become `Refused`.

Professor-set Market Prices are visible to banks as quoting context. They prefill the bank trade declaration price, but do not create a separate trade with the market.

## Project Structure

```text
app.py
db.py
models.py
seed.py
matching.py
analytics.py
ui.py
pages/
  company.py
  bank.py
  professor.py
```
