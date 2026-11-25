# edf-lab
a Python script that estimates the probability of default (PD) of a listed company. It pulls financial data with yfinance. It then maps the result to a credit rating using a custom score-to-rating table.

# EDF Merton

Estimate the Expected Default Frequency (EDF) of a listed company with the Merton structural model. Market and balance sheet data come from [yfinance](https://github.com/ranaroussi/yfinance). The script ends with a credit-style rating.

One script. Type a ticker, get a rating.

> The script's output and code comments are in French.

## How it works

The Merton model treats a company's equity as a call option on its assets. The debt is the strike price. If the assets are worth less than the debt at the horizon, the company defaults.

Equity value and equity volatility are observable. Asset value and asset volatility are not. The script solves two equations for those two unknowns:

```
E     = V_A·N(d1) − D·e^(−rT)·N(d2)
σ_E   = (V_A / E) · N(d1) · σ_A
```

Then it computes:

```
DD            = (ln(V_A / D) + (r − ½σ_A²)·T) / (σ_A·√T)
EDF théorique = N(−DD)
```

The script then turns DD into an "empirical" EDF with a lookup table, and the empirical EDF into a rating.

## Pipeline

| Step | What the script does |
|------|----------------------|
| 1 | Reads a Yahoo Finance ticker from the keyboard (`input()`). |
| 2 | Downloads 1 year of adjusted closes. Computes σ_E from daily log returns × √252. |
| 3 | Reads market cap (E) and the listing and reporting currencies. |
| 4 | If the two currencies differ, fetches an FX rate (`{fin}{stock}=X`, or the inverse pair) and converts the debt to the listing currency. |
| 5 | Picks the risk-free rate r (see below). |
| 6 | Reads short-term and long-term debt from the balance sheet. Sets the default point D = short-term debt + 0.5 × long-term debt. |
| 7 | Solves for V_A and σ_A with `scipy.optimize.fsolve`. |
| 8 | Computes DD, the theoretical EDF, the empirical EDF and the rating. |

Horizon T is fixed at 1 year.

### Risk-free rate

| Listing currency | Source | Fallback |
|------------------|--------|----------|
| USD | `^TNX` (US 10-year), previous close | 4% |
| EUR | `MFR10.AS` (France 10-year), previous close | 3% |
| Any other | none | 3% flat |

### Debt fields read from yfinance

| Item | Row names tried, in order |
|------|---------------------------|
| Short-term debt | `Current Debt And Capital Lease Obligation`, `Current Debt` |
| Long-term debt | `Long Term Debt And Capital Lease Obligation`, `Long Term Debt` |

The script uses the most recent value yfinance returns for the row.

## Install

```bash
pip install yfinance numpy pandas scipy
```

## Usage

```bash
python "modélisation de EDF.py"
```

The script prompts for a ticker in Yahoo Finance format. Examples: `AAPL`, `MC.PA`, `7203.T`.

Output (labels are in French; values omitted here):

```
=== RÉSULTATS POUR <ticker> (<currency>) ===
Conversion FX (<fin> -> <stock>)   : ...
Taux sans risque utilisé (r)   : ...
Capitalisation boursière (E)   : ...
Dette Court Terme              : ...
Dette Long Terme               : ...
Default Point (D)              : ...
--------------------------------------------------
Valeur des actifs (V_A)        : ...
Volatilité des actions (sig_E) : ...
Volatilité des actifs (sig_A)  : ...
Distance au Défaut (DD)        : ...
EDF Théorique (Loi Normale)    : ...
EDF Empirique (Approche KMV)   : ...
Notation : ...
```

## Scales

### DD → empirical EDF

A hard-coded step function, inspired by the KMV approach. The values are fixed in the script. They do not come from Moody's default database.

| DD | Empirical EDF |
|----|---------------|
| ≥ 8.0 | 0.01% |
| ≥ 6.0 | 0.03% |
| ≥ 4.5 | 0.15% |
| ≥ 3.0 | 0.75% |
| ≥ 2.0 | 3.50% |
| ≥ 1.0 | 12.00% |
| < 1.0 | 25.00% |

### Empirical EDF → rating

| EDF (%) | Rating |
|---------|--------|
| ≤ 0.02 | AAA / AA+ (Prime) |
| ≤ 0.05 | AA / A+ (High Grade) |
| ≤ 0.12 | A / A- (Upper Medium Grade) |
| ≤ 0.40 | BBB+ / BBB- (Lower Medium Grade) |
| ≤ 1.50 | BB+ / BB- (Speculative) |
| ≤ 5.00 | B+ / B- (Highly Speculative) |
| > 5.00 | CCC - C (High Default Risk) |

The rating uses the empirical EDF, not the theoretical one. Because the empirical EDF takes only 7 values, the rating takes only 6 values. See the first known issue below.

## Known issues and limitations

Read these before you trust an output.

- **The "A / A-" band is unreachable.** The empirical EDF jumps from 0.03% to 0.15%. No value falls between 0.05% and 0.12%, so no company can ever get that rating.
- **The rating is coarse.** It depends on a 7-step lookup, not on the continuous EDF.
- **The theoretical EDF is risk-neutral.** The drift is the risk-free rate, so it overstates real-world default frequency. Strong companies get very small values.
- **No convergence check.** `fsolve` runs, and the script uses whatever it returns. A failed solve can still print numbers.
- **Missing debt rows count as zero.** If one debt row is absent, the script treats it as 0 and carries on. It stops only when both are missing.
- **Maturity mismatch.** The horizon is 1 year, but r is a 10-year yield.
- **Silent fallbacks for r.** If Yahoo returns nothing for the rate ticker, the script uses 4% (USD) or 3% (everything else) without a message.
- **Balance sheet lag.** Market cap is current. Debt comes from the latest annual statement, which can be many months old.
- **Naive volatility.** One year of daily returns. One earnings shock can move the result.
- **Banks and insurers.** Their debt is their business. The model does not apply to them.
- **GBp listings are untested.** The script renames `GBp` to `GBP` and divides market cap by 100. Afterwards the currencies may match, yet it still looks up an FX pair such as `GBPGBP=X`, which may fail. Check this before you use a London ticker.
- **Not a library.** There are no functions to import. Everything runs at the top level and waits on `input()`.
- **yfinance is a scraper.** Row names and fields change without notice. Pin your yfinance version.
- **`pandas` is imported but never used.**

## References

- Merton, R. C. (1974). On the Pricing of Corporate Debt: The Risk Structure of Interest Rates. *Journal of Finance*, 29(2).
- Crosbie, P. and Bohn, J. (2003). *Modeling Default Risk*. Moody's KMV.

## Disclaimer

This is an educational tool. It is not investment advice or a credit rating. Do not use it for lending or trading decisions.
