import numpy as np
import pandas as pd
from scipy.optimize import fsolve
from scipy.stats import norm
import yfinance as yf

# ==========================================
# 1. PARAMÈTRES (Modifiez uniquement le ticker)
# ==========================================
ticker_symbol = input()  # Testez avec ticker au format yahoo finance
T = 1.0  # Horizon standard d'1 an

# ==========================================
# 2. DONNÉES DE MARCHÉ & VOLATILITÉ (sigma_E)
# ==========================================
ticker = yf.Ticker(ticker_symbol)
info = ticker.info

df = yf.download(
    ticker_symbol, period='1y', auto_adjust=False, progress=False)

close_prices = df['Adj Close'].squeeze()
log_returns = np.log(close_prices / close_prices.shift(1)).dropna()
sigma_E = float(log_returns.std() * np.sqrt(252))

# Capitalisation boursière (E) et devises
E = float(info.get('marketCap'))
stock_curr = info.get('currency')  # Devise de l'action (ex: USD)
fin_curr = info.get('financialCurrency')  # Devise du bilan (ex: JPY)

# ==========================================
# 3. CONVERTISSEUR DYNAMIQUE DE DEVISES (FX)
# ==========================================
fx_rate = 1.0
if stock_curr and fin_curr and stock_curr != fin_curr:
    # Gestion des sous-unités (ex: GBp -> GBP)
    if stock_curr == 'GBp':
        stock_curr = 'GBP'
        E /= 100.0

    fx_ticker = f'{fin_curr}{stock_curr}=X'
    fx_hist = yf.Ticker(fx_ticker).history(period='5d')

    if not fx_hist.empty:
        fx_rate = float(fx_hist['Close'].dropna().to_numpy()[-1])
    else:
        # Tentative avec taux inversé si la paire directe n'existe pas
        inv_ticker = f'{stock_curr}{fin_curr}=X'
        inv_hist = yf.Ticker(inv_ticker).history(period='5d')
        if not inv_hist.empty:
            fx_rate = 1.0 / float(inv_hist['Close'].dropna().to_numpy()[-1])
        else:
            raise ValueError(
                f'Impossible de récupérer le taux de change {fin_curr} -> {stock_curr}'
            )

# ==========================================
# 4. TAUX SANS RISQUE DYNAMIQUE (r)
# ==========================================
if stock_curr == 'USD':
    rf_ticker = yf.Ticker('^TNX')  # US Treasury 10 ans
    rf_val = rf_ticker.info.get('previousClose')
    r = (rf_val / 100) if rf_val else 0.04
elif stock_curr == 'EUR':
    rf_ticker = yf.Ticker('MFR10.AS')  # OAT France 10 ans
    rf_val = rf_ticker.info.get('previousClose')
    r = (rf_val / 100) if rf_val else 0.03
else:
    r = 0.03  # Taux par défaut pour les autres devises

# ==========================================
# 5. EXTRACTION DES DETTES & CONVERSION
# ==========================================
balance_sheet = ticker.balance_sheet


def get_debt(bs, possible_names):
    for name in possible_names:
        if name in bs.index:
            val = bs.loc[name].dropna()
            if not val.empty:
                return float(val.to_numpy()[0])
    return 0.0


short_term_debt_raw = get_debt(balance_sheet,
    [
        "Current Debt And Capital Lease Obligation", "Current Debt"
    ],
)

long_term_debt_raw = get_debt(balance_sheet,
    [
     "Long Term Debt And Capital Lease Obligation", "Long Term Debt"
    ],
)

# Conversion des dettes dans la devise de la capitalisation boursière
short_term_debt = short_term_debt_raw * fx_rate
long_term_debt = long_term_debt_raw * fx_rate

# Calcul des dettes pour l'equation du système de Merton
D = short_term_debt + 0.5 * long_term_debt

if D == 0:
    raise ValueError(f'Aucune dette trouvée pour {ticker_symbol}.')


# ==========================================
# 6. RÉSOLUTION DU SYSTÈME DE MERTON (V_A, sigma_A)
# ==========================================
def merton_equations(vars, E, sigma_E, D, r, T):
    V_A, sigma_A = vars
    if V_A <= 0 or sigma_A <= 0:
        return [1e10, 1e10]

    d1 = (np.log(V_A / D) + (r + 0.5 * sigma_A**2) * T) / (sigma_A * np.sqrt(T)) # D1 de Black-Scholes-Merton

    d2 = d1 - sigma_A * np.sqrt(T) # D2 de Black-Scholes-Merton

    eq1 = V_A * norm.cdf(d1) - D * np.exp(-r * T) * norm.cdf(d2) - E # Equation menant à E (Market value of equity)
    eq2 = (V_A / E) * norm.cdf(d1) * sigma_A - sigma_E # Equation menant à la volatilité des capitaux sigma_A

    return [eq1, eq2]


initial_guess = [E + D, sigma_E * (E / (E + D))]
V_A, sigma_A = fsolve(merton_equations, initial_guess, args=(E, sigma_E, D, r, T))

# ==========================================
# 7. CALCUL DE LA DISTANCE AU DÉFAUT & EDF
# ==========================================
DD = (np.log(V_A / D) + (r - 0.5 * sigma_A**2) * T) / (sigma_A * np.sqrt(T))
EDF_theorique = norm.cdf(-DD)


def empirical_edf(dd):
    if dd >= 8.0:
        return 0.0001 
    elif dd >= 6.0:
        return 0.0003
    elif dd >= 4.5:
        return 0.0015
    elif dd >= 3.0:
        return 0.0075
    elif dd >= 2.0:
        return 0.0350
    elif dd >= 1.0:
        return 0.1200
    else:
        return 0.2500


def edf_to_notation(edf_pct):
    if edf_pct <= 0.02:
        return "AAA / AA+ (Prime)"
    elif edf_pct <= 0.05:
        return "AA / A+ (High Grade)"
    elif edf_pct <= 0.12:
        return "A / A- (Upper Medium Grade)"
    elif edf_pct <= 0.40:
        return "BBB+ / BBB- (Lower Medium Grade)"
    elif edf_pct <= 1.50:
        return "BB+ / BB- (Speculative)"
    elif edf_pct <= 5.00:
        return "B+ / B- (Highly Speculative)"
    else:
        return "CCC - C (High Default Risk)"

EDF_empirique = empirical_edf(DD)
EDF_notation = edf_to_notation(EDF_empirique * 100)


# ==========================================
# 8. AFFICHAGE DES RÉSULTATS
# ==========================================
print(f'=== RÉSULTATS POUR {ticker_symbol} ({stock_curr}) ===')
if stock_curr != fin_curr:
    print(f'Conversion FX ({fin_curr} -> {stock_curr})   : {fx_rate:.6f}')
print(f'Taux sans risque utilisé (r)   : {r:.2%}')
print(f'Capitalisation boursière (E)   : {E:,.0f} {stock_curr}')
print(f'Dette Court Terme              : {short_term_debt:,.0f} {stock_curr}')
print(f'Dette Long Terme               : {long_term_debt:,.0f} {stock_curr}')
print(f'Default Point (D)              : {D:,.0f} {stock_curr}')
print('-' * 50)
print(f'Valeur des actifs (V_A)        : {V_A:,.0f} {stock_curr}')
print(f'Volatilité des actions (sig_E) : {sigma_E:.2%}')
print(f'Volatilité des actifs (sig_A)  : {sigma_A:.2%}')
print(f'Distance au Défaut (DD)        : {DD:.2f} écarts-types')
print(f'EDF Théorique (Loi Normale)    : {EDF_theorique:.6%}')
print(f'EDF Empirique (Approche KMV)   : {EDF_empirique:.2%}')
print(f'Notation : {EDF_notation:}' )

