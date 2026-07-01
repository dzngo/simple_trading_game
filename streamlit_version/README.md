# Options Trading Game - Streamlit Version

A lightweight Streamlit MVP for a university finance course. Students play as companies or banks, while a professor supervises the game and controls option definitions and Market Prices.

The app intentionally avoids real option pricing, Greeks, implied volatility, exercise logic, and Black-Scholes. Options are classroom instruments with manually controlled bid/ask prices and simple payoff formulas for professor-facing analysis.

## Features

- Simple login by selecting a demo user
- Company page for trade declarations with banks
- Bank page for trade declarations with companies and direct market trades at professor-set bid/ask prices
- Professor page for order/trade supervision, price configuration, reset, and Plotly analytics
- SQLite persistence
- Matching engine requiring compatible independent declarations
- Refused status when reciprocal company-bank declarations disagree
- Live dashboard sections refresh automatically every 5 seconds

## Refined Project Outline

The next iteration should support a professor-configured option universe instead of only fixed `Call` and `Put` products.

The professor should be able to choose the number of active options, ideally from 1 to 20. Each option has:

- option type: `Call` or `Put`
- underlying asset: professor-entered text, about 30 characters
- strike price: integer, displayed with `€` where useful
- market ask price: one-decimal numeric value, the price at which banks buy from the market
- market bid price: one-decimal numeric value, the price at which banks sell to the market

Visibility rules:

- Companies see only option type, underlying asset, and strike price.
- Banks see option type, underlying asset, strike price, market ask, and market bid.
- The professor sees and edits all fields.

Market price updates should be staged. The professor can edit many bid/ask values without immediately changing bank screens. Pressing `Adjust market prices` publishes all valid changes together. Bid and ask must be positive, and ask must be strictly greater than bid. If any option is invalid, show an error and publish none of the staged changes.

Option setup applies immediately before trading starts. Trading starts with the first submitted declaration. After that point, option definitions and active option count are locked, and only market bid/ask prices remain adjustable.

The professor dashboard should also include a per-group trade summary:

- select a company or bank
- list matched company-bank trades involving that group
- allow selection of relevant trades
- compute total prices paid for selected buy trades
- compute total prices received for selected sell trades
- plot the sum of selected trade payoffs as a function of final underlying price `x`

Payoff formulas:

- Call with strike `K`: `max(x - K, 0)`
- Put with strike `K`: `max(K - x, 0)`

For the selected group, bought options add payoff and sold options subtract payoff.

Selected payoff trades must share the same underlying asset. A single `x` only has a clear meaning when all selected trades refer to the same underlying final price.

## Setup From This Folder

```bash
cd streamlit_version
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
streamlit run app.py
```

You can also run it from the repository root:

```bash
streamlit run streamlit_version/app.py
```

The SQLite database path is anchored to this folder, so the app uses `streamlit_version/trading_game.db`.

## Demo Users

- Company A
- Company B
- Bank X
- Bank Y
- Professor

## Trading Rules

A trade matches when two pending declarations have:

- the same option
- the same price
- opposite sides
- reciprocal counterparties

If a reciprocal declaration exists for the same company, bank, and option but the side or price does not match, the new declaration and the oldest mismatched reciprocal declaration become `Refused`.

Company-bank declarations are hidden before matching. Companies and banks negotiate verbally outside the app, then independently enter the agreed terms. The app only validates whether those declarations match and shows an error/refusal if the entered terms differ.

Negotiated company-bank prices use one decimal place unless the professor later asks for a different precision. Matching requires exact equality at the app's displayed precision.

Professor-set Market Prices are visible to banks as quoting context.

Market trading behavior:

- Banks can trade directly with the market.
- A bank buying from the market uses the selected option's published ask price.
- A bank selling to the market uses the selected option's published bid price.
- Banks cannot override the published market trade price.
- Market trades are validated immediately and do not require reciprocal counterparty declarations.
- Market trades are stored and displayed to the professor in a separate `Market Transactions` table.
- Market trades are included in professor cumulative P/L analytics.
- Market trades are excluded from the selected group payoff summary.
- Companies cannot trade directly with the market and cannot see market bid/ask prices.

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
