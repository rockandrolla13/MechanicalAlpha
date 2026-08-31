# RFQ Event Table

| Input | Example | Why It Matters |
| --- | --- | --- |
| `rfq_id` | unique RFQ key | event tracking |
| `timestamp` | `2026-08-29 10:31:22` | as-of feature construction |
| `ISIN` / bond ID | `US...` | bond-level alpha |
| `issuer` | Ford, Verizon, JPM | issuer spillover |
| `side` | client sells / client buys | directional pressure |
| `size` | `$1mm`, `$5mm`, `$25mm` | notional pressure |
| `venue` | MarketAxess, Tradeweb, Bloomberg | venue-specific behavior |
| `protocol` | list RFQ, single-name RFQ, click-to-trade | liquidity / information content |
| `number_of_dealers` | 3, 5, all-to-all | competition / leakage proxy |
| `request_type` | firm / indicative | signal strength |
| `quote_time` | when you respond | latency / market state alignment |
