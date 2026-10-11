# Submission form — Kestrel Home Returns Risk (Variant A)

> The brief references a form whose template was not in the pack. This file answers every field the brief names; copy into the official form if one is supplied.

**Submitted by:** Anindya Gupta · **Date:** 11 Oct 2026 · **Repo root contains:** code, README, MEMO.md, predictions.csv

## 1. Expected score on the hidden outcomes — written before sending
- **Expected ROC-AUC: 0.78 (likely range 0.76–0.80).**
- **Why:** three rolling out-of-time quarters scored 0.768 / 0.773 / 0.789, pooled 0.777 (bootstrap 95% CI 0.757–0.795). The test quarter (Jul–Sep 2026) directly follows the last validation quarter, same columns, no value glitch, and the model was refit on all 15 months.
- If scored on **log-loss**: ~0.29–0.30 (backtest 0.292–0.301). **Brier:** ~0.085. Scores are calibrated probabilities (mean 0.119 on test vs 11.4% historic return rate).
- If scored on **accuracy at 0.5**: ~89%, barely above the 88.5% of predicting "no return" for everyone — which is why I don't optimise for it.
- **Risk to the estimate:** Jul–Sep includes Raksha Bandhan/early festive gifting; only one festive season in history. A drop toward 0.75 would not surprise me.

## 2. What I used
- Python 3, pandas, NumPy, scikit-learn (logistic regression; gradient boosting for comparison), matplotlib — training only.
- Service: Python standard library only (`http.server`, `json`). No framework, no database.
- No external data. No model API / LLM in the product.
- AI coding assistant (Claude) used to help write code and documents; all numbers come from scripts in the repo and were checked against their outputs.

## 3. What it cost
- Compute: a laptop; full training + backtest < 1 minute. **Rs 0 per scored order.**
- Paid APIs: none. Licences: none (all open-source).
- Operating cost for Kestrel: only the confirmation calls — ~Rs 15 per order on average at the 11.2% threshold (≈32% of orders × Rs 45).

## 4. What I discarded (and why)
| Discarded | Why |
|---|---|
| `pickup_scheduled_at`, `last_service_event_type` | Recorded after a return is raised; 0.99 AUC in backtest, empty at dispatch |
| "95% accuracy" as the goal | Flag-nothing scores 88.6%; metric can't tell good from useless |
| Hold-at-dispatch action | Loses ~12% of held good orders; calls beat holds at every threshold |
| Gradient boosting | Lower out-of-time AUC in all 3 quarters (avg 0.75 vs 0.78), harder to explain |
| `order_value_inr` | Oct-2025 values stored ×100; list price × qty replaces it |
| 651 partner-feed duplicate rows | Exact repeats of CRM rows |
| `delivery_note` text | No signal; untrusted free text |
| Month/seasonality features | One season of history |
| Ritu's Rs 600 return cost | Finance/policy figure is Rs 1,150 |
| Random train/test split | Overstates performance vs next-quarter use |

## 5. Decisions on ambiguities
See `DECISIONS.md` (17 entries: decided → written → why).
