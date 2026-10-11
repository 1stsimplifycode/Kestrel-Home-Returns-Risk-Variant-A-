"""Kestrel returns-risk scorer. Pure standard library: no installs needed to score.

Feature building lives here so training (train.py) and serving (serve.py) use identical code.
"""
import json, math, os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# Policy v4.1 §4/§7 numbers. Change here, nowhere else.
COST_RETURN = 1150      # Rs per returned order (Finance figure, not the Rs 600 in the first email)
COST_CALL = 45          # Rs per completed pre-dispatch call
CALL_PREVENTS = 0.35    # share of would-be returns a call prevented in the spring pilot (unverified, see MEMO)
HOLD_CANCEL = 0.12      # share of >24h holds the customer cancels
CALL_THRESHOLD = COST_CALL / (CALL_PREVENTS * COST_RETURN)   # ~0.112: above this a call pays for itself

PAYMENT = ["cod", "emi", "prepaid_card", "prepaid_upi"]
CHANNEL = ["app", "web", "marketplace", "partner_outlet"]
FAMILY = ["Air Fryer", "Ceiling Fan", "Induction Cooktop", "Mixer Grinder",
          "Robot Vacuum", "Room Heater", "Water Purifier"]

# Columns deliberately NOT used: see DECISIONS.md
#   last_service_event_type, pickup_scheduled_at -> written AFTER a return starts (leak)
#   order_value_inr -> Oct-2025 rows stored x100 by the new gateway; list price x qty carries the same info
#   delivery_note -> free text, no signal after templating, untrusted content
#   order_placed_at month -> 15 months only, seasonality would not transfer

READABLE = {
    "payment_mode=emi": "Paid on EMI", "payment_mode=prepaid_card": "Prepaid by card",
    "payment_mode=prepaid_upi": "Prepaid by UPI", "payment_mode=cod": "Cash on delivery",
    "sales_channel=web": "Ordered on website", "sales_channel=marketplace": "Ordered via marketplace",
    "sales_channel=partner_outlet": "Sold at partner outlet", "sales_channel=app": "Ordered in app",
    "discount": "Discount at checkout", "gift": "Marked as a gift",
    "shield": "Kestrel Shield member (free returns)",
    "prior_returns": "Customer has returned before", "prior_orders": "Customer's order history",
    "no_address": "No delivery address captured", "log_price": "Order value (list price x qty)",
    "promised_days": "Long promised delivery time", "qty2": "More than one unit",
    "tenure_yrs": "How long the customer has been signed up", "night": "Ordered between midnight and 6 am",
}


def _family_of(sku):
    code = (sku or "").split("-")[1] if sku and sku.count("-") >= 2 else ""
    return {"AF": "Air Fryer", "CF": "Ceiling Fan", "IC": "Induction Cooktop", "MG": "Mixer Grinder",
            "RV": "Robot Vacuum", "RH": "Room Heater", "WP": "Water Purifier"}.get(code, "")


def build_features(rec, products, customers=None):
    """rec: dict with raw order columns. products: {sku: {...}}. customers: {customer_id: {...}} or None.
    Shield / signup may be passed directly on rec (shield_member, signup_date) to avoid a lookup."""
    prod = products.get(rec.get("sku"), {})
    cust = (customers or {}).get(rec.get("customer_id"), {})
    shield = rec.get("shield_member", cust.get("shield_member", "N"))
    signup = rec.get("signup_date", cust.get("signup_date"))
    fam = prod.get("family") or _family_of(rec.get("sku"))
    qty = int(float(rec.get("qty") or 1))
    price = float(prod.get("list_price_inr") or 0) or float(rec.get("list_price_inr") or 0)
    if price <= 0:
        raise ValueError("unknown sku and no list_price_inr given")
    ts = _parse_ts(rec.get("order_placed_at"))
    x = {}
    for v in PAYMENT[1:]:
        x["payment_mode=" + v] = 1.0 if rec.get("payment_mode") == v else 0.0
    for v in CHANNEL[1:]:
        x["sales_channel=" + v] = 1.0 if rec.get("sales_channel") == v else 0.0
    for v in FAMILY[1:]:
        x["family=" + v] = 1.0 if fam == v else 0.0
    x["discount"] = float(rec.get("discount_pct") or 0) / 10
    x["gift"] = 1.0 if str(rec.get("is_gift", "N")).upper() == "Y" else 0.0
    x["shield"] = 1.0 if str(shield).upper() == "Y" else 0.0
    x["prior_returns"] = float(min(int(float(rec.get("customer_prior_returns") or 0)), 4))
    x["prior_orders"] = math.log1p(float(rec.get("customer_prior_orders") or 0))
    x["no_address"] = 1.0 if int(float(rec.get("delivery_pincode") or 0)) == 0 else 0.0
    x["log_price"] = math.log(price * qty)
    x["promised_days"] = float(rec.get("promised_delivery_days") or 5) / 3
    x["qty2"] = 1.0 if qty > 1 else 0.0
    if signup and ts:
        x["tenure_yrs"] = max((ts - datetime.strptime(str(signup)[:10], "%Y-%m-%d")).days, 0) / 365
    else:
        x["tenure_yrs"] = 1.0
    x["night"] = 1.0 if ts and ts.hour < 6 else 0.0
    return x


def _parse_ts(s):
    if not s:
        return None
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(s)[:19], f)
        except ValueError:
            pass
    return None


def load_reference(path=None):
    """Product table is small and committed (data/products.csv). Customer table is optional."""
    import csv
    path = path or os.path.join(HERE, "data", "products.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return {r["sku"]: r for r in csv.DictReader(f)}


class Scorer:
    def __init__(self, model_path=None, products=None):
        with open(model_path or os.path.join(HERE, "model.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.coef, self.intercept, self.means = m["coef"], m["intercept"], m["means"]
        self.products = products or load_reference()

    def score(self, rec, customers=None):
        x = build_features(rec, self.products, customers)
        z = self.intercept + sum(self.coef[k] * x[k] for k in self.coef)
        p = 1 / (1 + math.exp(-z))
        return p, x

    def explain(self, rec, customers=None, top=3):
        p, x = self.score(rec, customers)
        contrib = {k: self.coef[k] * (x[k] - self.means[k]) for k in self.coef}
        # one-hot groups are explained as one factor named after the order's actual value
        name = dict(READABLE)
        fam = self.products.get(rec.get("sku"), {}).get("family") or _family_of(rec.get("sku")) or "unknown"
        actual = {"payment_mode": READABLE.get("payment_mode=" + str(rec.get("payment_mode")), "Payment type"),
                  "sales_channel": READABLE.get("sales_channel=" + str(rec.get("sales_channel")), "Sales channel"),
                  "family": "Product type: " + fam}
        for g, label in actual.items():
            keys = [k for k in contrib if k.startswith(g + "=")]
            contrib[g] = sum(contrib.pop(k) for k in keys)
            name[g] = label
        NEG = {"shield": "Not a Shield member", "prior_returns": "No previous returns", "gift": "Not a gift",
               "promised_days": "Short promised delivery time", "discount": "Little or no discount",
               "log_price": "Lower-value order", "no_address": "Delivery address captured",
               "prior_orders": "Few previous orders"}
        for k, lbl in NEG.items():
            if k in contrib and contrib[k] < 0:
                name[k] = lbl
        if contrib.get("promised_days", 0) > 0:
            name["promised_days"] = "Long promised delivery time"
        if contrib.get("discount", 0) > 0:
            name["discount"] = "High discount at checkout"
        if contrib.get("log_price", 0) > 0:
            name["log_price"] = "High-value order"
        ups = sorted([(v, k) for k, v in contrib.items() if v > 0.05], reverse=True)[:top]
        downs = sorted([(v, k) for k, v in contrib.items() if v < -0.05])[:top]
        shield = x["shield"] == 1.0
        if p >= CALL_THRESHOLD:
            action = "CALL BEFORE DISPATCH"
            why = ("Expected saving from a call is Rs %.0f vs Rs %d call cost." %
                   (p * CALL_PREVENTS * COST_RETURN, COST_CALL))
        else:
            action = "SHIP NORMALLY"
            why = ("A call would cost Rs %d but save only about Rs %.0f on this order." %
                   (COST_CALL, p * CALL_PREVENTS * COST_RETURN))
        if shield and action.startswith("CALL"):
            why += " Shield member: courtesy call only - never hold."
        return {
            "return_probability": round(p, 4),
            "risk_band": "high" if p >= 0.30 else "medium" if p >= CALL_THRESHOLD else "low",
            "recommended_action": action,
            "why_this_action": why,
            "raises_risk": [name.get(k, k) for _, k in ups],
            "lowers_risk": [name.get(k, k) for _, k in downs],
            "hold_dispatch": False,
            "note": "Model never recommends a hold: a hold loses ~12% of orders to cancellation and "
                    "prevents no return by itself. See MEMO.md.",
        }
