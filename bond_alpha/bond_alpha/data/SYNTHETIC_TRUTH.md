# Synthetic Tape Truth

The synthetic tape is for end-to-end testing without WRDS, FINRA licensing, or proprietary RFQ data.
It is not a market simulator for calibration.

## Data Generating Process

- Universe: 500 synthetic CUSIPs by default.
- Calendar: business days between the configured start and end dates.
- Arrivals: marked point processes approximated with self-exciting daily intensities.
- Trade signs: buy/sell signs have persistence.
- Prices: issuer-curve fair value plus OU pressure, signed-print impact, issuer lead-lag, and noise.
- Contra party type: mostly customer prints, with occasional interdealer prints.

## Planted Effects

All signs use the project convention.
`side_flag = +1` means the client sells to the dealer.
`side_flag = -1` means the client buys from the dealer.

### High-Volume Reversal

Large signed prints create short-term pressure.
The default magnitude is `-7.5` basis points per `side_flag * log1p(par_volume / 1MM)`.
This plants reversal after high-volume customer selling or buying.

Expected positive-control factor:
recent high-volume client selling should predict positive later reversal after the pressure decays.

### Sign Persistence

The default same-sign continuation probability is `0.68` after a signed print.
This creates clustered customer flow.

Expected positive-control factor:
recent signed flow should predict near-term same-direction flow.

### Liquid-to-Illiquid Issuer Lead-Lag

Issuer pressure carries over across bonds through a persistent issuer state.
The default magnitude is `4.0` basis points times the issuer pressure state.
Liquid bonds update the issuer state more often.
Illiquid bonds therefore inherit stale pressure after related bonds trade.

Expected positive-control factor:
liquid-bond issuer flow should predict subsequent illiquid-bond price movement within the same issuer.

## Liquidity Calibration

The default parameters target:

- median bond trading frequency near `2` trades per day
- 10th percentile bond trading frequency near `2` trades per week

Realized counts vary by random seed and sample window.

## Leakage Notes

The generator emits only trade-time rows.
It does not emit future labels.
Downstream tests must still build targets strictly after each prediction timestamp.
