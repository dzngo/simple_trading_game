# Build a Simplified Options Trading Game — University Course MVP

Build a lightweight web application for a university finance course.

The application is a simplified trading simulation game where students play either:
- Companies
- Banks

A professor/admin supervises the game.

The goal is educational:
- understand negotiated company-bank trading
- understand trade matching
- understand market makers
- understand bid/ask prices
- understand trading workflows

Do NOT implement real option pricing models, Black-Scholes, Greeks, implied volatility, or exercise mechanics.

For the refined MVP:
- Tradable options are configured by the professor before or during the simulation.
- Each option is a classroom instrument with a manually defined type, underlying asset, strike price, bid price, and ask price.
- Payoff charts use only the basic payoff formulas for calls and puts. Do not implement real option pricing models, Black-Scholes, Greeks, implied volatility, or exercise mechanics.

# Recommended Stack

Use:
- Python
- Streamlit
- SQLite
- Plotly
- SQLAlchemy if useful

The implementation should prioritize:
- simplicity
- robustness
- readability
- ease of demonstration during class

# Core Roles

There are 3 user roles:
1. Company
2. Bank
3. Professor/Admin

# Core Concept

Trades between companies and banks are negotiated trades.

A trade is only validated if BOTH counterparties independently enter compatible declarations.

Example:

Company A enters:
- Option: Call on Asset A, strike 100
- Side: Buy
- Price: 10
- Counterparty: Bank X

Bank X enters:
- Option: Call on Asset A, strike 100
- Side: Sell
- Price: 10
- Counterparty: Company A

Then:
- the trade becomes matched
- both orders are marked as matched
- the trade is recorded

If no compatible order exists:
- the order remains pending

# Options

The professor/admin should be able to choose how many options are available for the simulation, ideally from 1 to 20.

Each option has 5 fields:

1. Option type
   - `Call` or `Put` only.

2. Underlying asset
   - Free text entered by the professor.
   - Limit to about 30 characters.
   - Copy/paste should work naturally.

3. Strike price
   - Numeric integer.
   - Display with a small `€` symbol where useful.

4. Market price ask
   - Numeric amount with one decimal place.
   - This is the price at which banks can buy the option from the market.
   - Display with a small `€` symbol where useful.

5. Market price bid
   - Numeric amount with one decimal place.
   - This is the price at which banks can sell the option to the market.
   - Display with a small `€` symbol where useful.

Visibility:
- Companies see fields 1 to 3 only: option type, underlying asset, and strike price.
- Banks see fields 1 to 5, including market bid/ask prices.
- The professor sees and edits all fields.

Market price validation:
- For every option, bid and ask must be positive.
- For every option, ask price must be strictly greater than bid price.
- If the professor tries to publish invalid market prices for any option, show an error and do not publish the changes.

The professor controls option definitions and market prices manually.

Option setup:
- The professor may configure option count, option type, underlying asset, and strike before trading starts.
- Trading starts with the first submitted declaration.
- Once trading has started, option definitions and active option count are locked. Only market bid/ask prices remain adjustable.

# Application Pages

The application should contain 3 main interfaces/pages.

---

# 1. Company Page

The company interface must allow:

## Features

- View available options:
  - option type
  - underlying asset
  - strike price

- View available banks

- Submit trade declarations:
  - option
  - side: Buy or Sell
  - agreed price
  - selected bank counterparty

- View:
  - pending orders
  - matched trades
  - trade history

## Notes

Companies:
- cannot trade directly with the market
- do not see market bid/ask prices
- do not see banks' hidden submitted declarations before a match or refusal
- do not see global analytics
- do not see PnL graphs

---

# 2. Bank Page

The bank interface must allow:

## Features

- View available options:
  - option type
  - underlying asset
  - strike price
  - market ask price
  - market bid price

- View available companies

- Submit trade declarations with companies

- Trade directly with the market

The market exposes:
- bid price per option
- ask price per option

defined by the professor.

## Market Trading Rules

If the bank buys from the market:
- use the ask price

If the bank sells to the market:
- use the bid price

Market trades should be instantly validated.
Banks can only buy or sell options with the market at the professor-set published bid/ask price. They cannot override the market trade price.

## Bank View

The bank page should display:
- pending orders
- matched trades
- trade history
- current market bid/ask prices

## Notes

Banks:
- act as intermediaries / market makers
- do not see global analytics
- do not see PnL graphs

---

# 3. Professor/Admin Page

The professor interface must allow:

## Features

- View all submitted orders
- View all matched trades
- View market transactions in a separate table
- View pending trades
- View unmatched/mismatched trades

- Configure the option universe:
  - number of active options, ideally 1 to 20
  - option type
  - underlying asset
  - strike price
  - market ask price
  - market bid price

- Stage market price changes before publishing:
  - the professor can edit many bid/ask values on screen
  - banks should continue seeing the last published prices while the professor is editing
  - pressing an `Adjust market prices` button publishes all valid staged price changes together
  - publishing fails with an error if any option has non-positive prices or ask price less than or equal to bid price

- Visualize cumulative gains/losses using graphs
  - include both company-bank trades and bank-market trades

- Visualize trading activity

- Summarize trades by group:
  - select a company or bank
  - show matched company-bank trades involving that group
  - allow the professor to select a subset of those trades
  - compute the sum of prices paid for selected buy trades
  - compute the sum of prices received for selected sell trades
  - show a payoff graph for the selected trades

- Reset game state if needed

## Graphs

Use Plotly to display:
- cumulative profit/loss per participant
- simple trading activity charts
- payoff curve for the professor-selected trades of one group

The professor page is the ONLY page showing global analytics and profit/loss graphs.

The cumulative profit/loss analytics include both:
- company-bank trades
- bank-market trades

The selected group payoff summary includes matched company-bank trades only.

## Payoff Graph

The payoff graph is a function of the final underlying price `x`.

For each selected trade:
- Call payoff with strike `K`: `max(x - K, 0)`
- Put payoff with strike `K`: `max(K - x, 0)`

The graph should show the sum of payoffs for the selected trades across a reasonable range of `x`.

All selected trades in one payoff chart must have the same underlying asset. A single `x` only makes sense when every selected trade refers to the same underlying final price.

Trade direction matters:
- If the selected group bought the option, add the payoff.
- If the selected group sold the option, subtract the payoff.

The graph does not need to model pricing, probabilities, discounting, volatility, maturity, or exercise behavior.

# Matching Engine

Implement a simple matching engine.

Matching conditions:
- same option
- same price
- opposite sides
- matching counterparties

If all conditions are met:
- create a trade
- mark both orders as matched

If a reciprocal declaration exists for the same option and counterparties but the side or price does not match:
- mark the new declaration and the oldest mismatched reciprocal declaration as refused
- show an error message explaining that the company and bank entered incompatible terms
- do not expose either side's hidden pending declaration terms as negotiation tooling

If no reciprocal declaration exists:
- keep the order pending

Matching should use the oldest compatible pending reciprocal declaration. A stale mismatched declaration should not block a newer compatible declaration.

Negotiated company-bank prices use one decimal place unless the professor later asks for a different precision. Matching requires exact equality at the app's displayed precision.

# Market Trading

Only banks can trade with the market.

The professor defines:
- market bid price
- market ask price

Market trades should:
- immediately create validated trades
- not require counterpart matching

If the bank buys from the market, the trade price is the option's published ask price.

If the bank sells to the market, the trade price is the option's published bid price.

Banks cannot override the published market trade price.

Only published market prices are visible to banks and used for market trades. Draft edits on the professor page should not affect bank screens until `Adjust market prices` succeeds.

Market transactions:
- are stored as trades with source `Market`
- display the market side as `Market`
- appear on the professor page in a separate `Market Transactions` table
- are included in professor cumulative P/L analytics
- are excluded from selected group payoff summaries

# Suggested Database Schema

## users
- id
- username
- role

## options
- id
- option_type: Call or Put
- underlying_asset
- strike_price
- is_active
- display_order

## orders
- id
- user_id
- counterparty_id
- option_id
- side
- price
- status
- created_at

## trades
- id
- option_id
- buyer_id
- seller_id
- price
- source: Client-Bank or Market
- created_at

For market trades, the market-side buyer or seller can be represented as nullable internally and displayed as `Market`.

## market_prices
- id
- option_id
- bid_price
- ask_price
- updated_at

## market_price_drafts
- id
- option_id
- draft_bid_price
- draft_ask_price
- updated_at

The draft table is optional. The same behavior can be implemented with Streamlit session state if the app remains single-process and local, but persisted drafts are safer if the app may be refreshed while the professor edits.

# UI Requirements

Use Streamlit multipage structure.

Pages:
- Company
- Bank
- Professor

The UI should prioritize:
- clarity
- simplicity
- educational usability

Use:
- tables
- status badges/colors
- simple forms
- Plotly charts on professor page only

Prefer compact layouts. Use row-based or column-based editors for option definitions and market prices to avoid vertical sprawl when up to 20 options are active.

# Login

Implement a simple login page:
- select username
- infer role automatically
- store current user in session state

No real authentication needed.

# Suggested Project Structure

```bash
trading_game/
│
├── app.py
├── db.py
├── models.py
├── seed.py
├── matching.py
├── analytics.py
├── README.md
│
├── pages/
│   ├── company.py
│   ├── bank.py
│   └── professor.py
```

# Seed Data

Create demo users:
- Company A
- Company B
- Bank X
- Bank Y
- Professor

Create demo options, for example:
- Call, underlying `Asset A`, strike 100, bid 9.0, ask 11.0
- Put, underlying `Asset A`, strike 100, bid 8.0, ask 10.0

The professor should be able to replace these with 1 to 20 active options.

# Expected Workflow

## Company-Bank Trade

1. User submits order
2. Save as Pending
3. Search for compatible opposite order
4. If found:
   - create Trade
   - mark both orders as Matched

## Market Trade

1. Bank selects Buy or Sell
2. Use published bid/ask market price for the selected option
3. Create Trade instantly

## Professor Price Adjustment

1. Professor edits one or more draft bid/ask values.
2. Banks continue seeing the last published values.
3. Professor clicks `Adjust market prices`.
4. Validate every active option:
   - ask price must be strictly greater than bid price
   - prices must be numeric and positive
5. If validation passes:
   - publish all draft prices together
   - banks see the new prices
6. If validation fails:
   - show an error identifying the invalid option
   - do not publish any of the draft price changes

# Deliverables

Generate:
- complete Streamlit application
- database models
- initialization scripts
- seed/demo data
- company-bank matching engine
- market trade logic
- professor analytics dashboard
- professor option configuration panel
- staged market price publishing with bid/ask validation
- professor group trade summary with selected-trade price totals and payoff graph
- separate professor market transactions table
- cumulative P/L analytics including both company-bank and market trades
- README with setup instructions

The application must run locally using:

```bash
streamlit run app.py
```

Keep the MVP simple and easy to explain during a university class demonstration.
