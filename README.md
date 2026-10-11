# Kestrel Home — Returns Risk (Variant A)

Scores each order before dispatch for return risk, explains why, and recommends **call** or **ship** (never hold).

| Deliverable | File |
|---|---|
| 1. Predictions (2,096 rows, `order_id,score`) | `predictions.csv` |
| 2. Service: endpoint + screen | `serve.py`, `static/index.html`, `kestrel_model.py`, `model.json` |
| 3. Evidence | `EVIDENCE.md`, `evidence/` |
| 4. Memo to Ritu | `MEMO.md` |
| 5. Screen-recording script (≤3 min) | `RECORDING_SCRIPT.md` |
| 6. Submission form | `SUBMISSION_FORM.md` |
| Decisions on ambiguities | `DECISIONS.md` |

## Run the service (clean machine, no API key, no installs)
Needs **Python 3.9+** only. Standard library — nothing to pip install.

**Windows:** double-click `run.bat` (starts the service and opens the browser).
**macOS / Linux:** `./run.sh` or `python3 serve.py`

Then open http://127.0.0.1:8000. Port busy? `python serve.py 8080`.

## Endpoint
`POST /score` — one order as JSON (raw columns from `test_unlabelled.csv`; `shield_member` and `signup_date` optional).

```bash
curl -s -X POST http://127.0.0.1:8000/score -H "Content-Type: application/json" -d "{\"order_id\":\"KO2610504\",\"sku\":\"KH-RV-02\",\"payment_mode\":\"cod\",\"sales_channel\":\"marketplace\",\"discount_pct\":20,\"qty\":1,\"promised_delivery_days\":8,\"customer_prior_orders\":2,\"customer_prior_returns\":1,\"is_gift\":\"N\",\"shield_member\":\"N\",\"delivery_pincode\":\"411001\",\"order_placed_at\":\"2026-09-20 14:10\"}"
```
Response: `return_probability`, `risk_band`, `recommended_action`, `why_this_action`, `raises_risk[]`, `lowers_risk[]`, `hold_dispatch:false`.
Errors: 400 for bad JSON / missing `sku`, `payment_mode`, `sales_channel` / unknown SKU. `GET /health` for liveness.

## Tests
`python -m unittest discover -s tests`

## Retrain / regenerate predictions and evidence
Needs the client CSVs in `data/` (git-ignored, Policy §10) and `pip install -r requirements-train.txt`.
`python train.py` → `model.json`, `predictions.csv`, `evidence/*`.

## How it works (short)
Logistic regression, 23 features available at dispatch (payment, channel, product family, discount, gift, Shield, prior returns/orders, value, promised days, tenure). Post-return columns dropped as leakage. Validated on three rolling out-of-time quarters: AUC 0.77–0.79. Call threshold = Rs 45 / (35% × Rs 1,150) = 11.2% risk. See `DECISIONS.md`.

## Data handling
Client data is confidential (Policy §10). Keep this repository **private**. Raw CSVs are excluded via `.gitignore`.
