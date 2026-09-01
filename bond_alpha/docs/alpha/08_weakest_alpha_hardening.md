# Weakest Alpha Hardening: Issuer Leader-Follower

Alpha: `leader_follower_pressure`

Location: `bond_alpha/src/bondalpha/features/leader_follower.py`

## Pre-Hardening Problem

The old implementation selected each issuer leader from full-sample activity.
It also computed rolling issuer pressure in row order.

That meant a future event could change historical leader identity.
It also meant the signal was not robust to input row order.

## Hardened Contract

At row `j`, the feature may use only:

- rows with the same scenario and issuer;
- event timestamps strictly before or equal only through the update order after the row is scored;
- prior activity counts to determine the leader;
- prior leader signed sizes to calculate pressure.

The feature must not use:

- future issuer activity;
- future notional thresholds;
- truth columns;
- simulator latent state;
- row order as a proxy for event time.

## Formula

For follower bond `i` in issuer `g`, define the prior leader:

```text
leader_g(t) = argmax_b N_b(t-)
```

where `N_b(t-)` counts prior public events only.

For non-leader rows:

```text
x_i(t) =
    sum_k w_k side_k sqrt(notional_k)
    / median_k |side_k sqrt(notional_k)|
```

over the last configured prior leader events.

Leader rows receive zero signal.

Positive signal means prior leader customer-buy pressure.

## Tests

Added:

- prior-only leader activity test;
- future mutation test;
- input-order invariance test.

