"""Clean data, backtest, fit final model, write model.json, predictions.csv and evidence/.
Needs: pandas, numpy, scikit-learn, matplotlib (requirements-train.txt). Serving does NOT need these.
Run:  python train.py
"""
import json, os
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss
import kestrel_model as km

D = os.path.join(km.HERE, "data")
EV = os.path.join(km.HERE, "evidence")
os.makedirs(EV, exist_ok=True)
rng = np.random.default_rng(7)

tr = pd.read_csv(f"{D}/train.csv", dtype={"delivery_pincode": str})
te = pd.read_csv(f"{D}/test_unlabelled.csv", dtype={"delivery_pincode": str})
cu = pd.read_csv(f"{D}/customers.csv")
products = km.load_reference(f"{D}/products.csv")
customers = cu.set_index("customer_id").to_dict("index")
log = {}

# ---- 1. Data audit / cleaning (each finding written to evidence/data_audit.json) ----
log["rows_raw"] = len(tr)
dups = tr[tr.order_id.duplicated(keep=False)]
log["partner_feed_duplicates_removed"] = int((tr.source == "partner_feed").sum())
log["duplicate_labels_agree"] = bool((dups.groupby("order_id").returned.nunique() == 1).all())
tr = tr[tr.source == "crm"].reset_index(drop=True)
lp = tr.sku.map(lambda s: float(products[s]["list_price_inr"]))
ratio = tr.order_value_inr / (lp * tr.qty * (1 - tr.discount_pct / 100))
log["order_value_x100_rows"] = int((ratio.round() == 100).sum())
log["order_value_x100_months"] = sorted(tr.loc[ratio.round() == 100, "order_placed_at"].str[:7].unique().tolist())
log["leak_columns"] = {
    "pickup_scheduled_at_present_return_rate": float(tr.loc[tr.pickup_scheduled_at.notna(), "returned"].mean()),
    "pickup_scheduled_at_present_in_test": int(te.pickup_scheduled_at.notna().sum()),
    "service_events_train": tr.last_service_event_type.value_counts().to_dict(),
    "service_events_test": te.last_service_event_type.value_counts().to_dict(),
}
log["pincode_000000_by_channel"] = tr[tr.delivery_pincode.astype(int) == 0].sales_channel.value_counts().to_dict()
log["rows_clean"] = len(tr)
log["base_return_rate"] = float(tr.returned.mean())

def feats(df):
    return pd.DataFrame([km.build_features(r, products, customers) for r in df.to_dict("records")])

X, y = feats(tr), tr.returned.values
Xte = feats(te)
cols = list(X.columns)

def lr():
    return LogisticRegression(C=1.0, max_iter=3000)

# ---- 2. Rolling-origin backtest: train on everything before a quarter, score that quarter ----
folds = [("2025-10-01", "2026-01-01"), ("2026-01-01", "2026-04-01"), ("2026-04-01", "2026-07-01")]
rows, oof_p, oof_y, oof_shield = [], [], [], []
for a, b in folds:
    trn = (tr.order_placed_at < a).values
    tst = ((tr.order_placed_at >= a) & (tr.order_placed_at < b)).values
    m = lr().fit(X[trn], y[trn])
    p = m.predict_proba(X[tst])[:, 1]
    g = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                       min_samples_leaf=40, random_state=0).fit(X[trn], y[trn])
    pg = g.predict_proba(X[tst])[:, 1]
    L = X.copy()
    L["pickup_booked"] = tr.pickup_scheduled_at.notna().astype(float)
    L["evt_reverse_pickup"] = (tr.last_service_event_type == "REVERSE_PICKUP").astype(float)
    pl = lr().fit(L[trn], y[trn]).predict_proba(L[tst])[:, 1]
    yt = y[tst]
    called = p >= km.CALL_THRESHOLD
    rows.append({
        "test_quarter": f"{a[:7]}..{b[:7]}", "n_test": int(tst.sum()), "return_rate": round(yt.mean(), 3),
        "auc_lr": round(roc_auc_score(yt, p), 3), "auc_gbm": round(roc_auc_score(yt, pg), 3),
        "auc_leaky_DISCARDED": round(roc_auc_score(yt, pl), 3),
        "acc_leaky_DISCARDED": round(((pl > .5) == yt).mean(), 3),
        "pr_auc_lr": round(average_precision_score(yt, p), 3),
        "brier_lr": round(brier_score_loss(yt, p), 4), "logloss_lr": round(log_loss(yt, p), 4),
        "accuracy_lr_at_0.5": round(((p > .5) == yt).mean(), 3),
        "accuracy_flag_nothing": round(1 - yt.mean(), 3),
        "share_called": round(called.mean(), 3),
        "returns_in_called_share": round(yt[called].sum() / max(yt.sum(), 1), 3),
        "net_saving_per_1000_orders_rs": round(1000 * (km.CALL_PREVENTS * km.COST_RETURN * yt[called].sum()
                                                       - km.COST_CALL * called.sum()) / len(yt)),
    })
    oof_p += list(p); oof_y += list(yt); oof_shield += list(X.loc[tst, "shield"])
bt = pd.DataFrame(rows)
bt.to_csv(f"{EV}/backtest_by_quarter.csv", index=False)
oof_p, oof_y, oof_shield = map(np.array, (oof_p, oof_y, oof_shield))

# bootstrap CI for pooled out-of-time AUC
bs = []
for _ in range(500):
    i = rng.integers(0, len(oof_y), len(oof_y))
    bs.append(roc_auc_score(oof_y[i], oof_p[i]))
log["oot_auc_pooled"] = round(roc_auc_score(oof_y, oof_p), 3)
log["oot_auc_95ci"] = [round(np.percentile(bs, 2.5), 3), round(np.percentile(bs, 97.5), 3)]

# ---- 3. What "accuracy" really buys: threshold sweep on out-of-time predictions ----
sweep = []
for t in [0.05, 0.08, km.CALL_THRESHOLD, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
    f = oof_p >= t
    tp, fp = int((f & (oof_y == 1)).sum()), int((f & (oof_y == 0)).sum())
    sweep.append({"threshold": round(t, 3), "flagged_share": round(f.mean(), 3),
                  "accuracy": round(((f) == oof_y).mean(), 3),
                  "precision": round(tp / max(tp + fp, 1), 3), "recall": round(tp / oof_y.sum(), 3),
                  "CALL_net_rs_per_1000": round(1000 * (km.CALL_PREVENTS * km.COST_RETURN * tp - km.COST_CALL * (tp + fp)) / len(oof_y)),
                  "HOLD_good_orders_lost_per_1000": round(1000 * km.HOLD_CANCEL * fp / len(oof_y), 1),
                  "HOLD_returns_avoided_per_1000": round(1000 * km.HOLD_CANCEL * tp / len(oof_y), 1)})
pd.DataFrame(sweep).to_csv(f"{EV}/threshold_sweep.csv", index=False)

# calibration by decile + Shield split
dec = pd.qcut(oof_p, 10, labels=False, duplicates="drop")
cal = pd.DataFrame({"decile": dec, "p": oof_p, "y": oof_y}).groupby("decile").agg(
    predicted=("p", "mean"), actual=("y", "mean"), n=("y", "size")).round(3)
cal.to_csv(f"{EV}/calibration_deciles.csv")
sh = []
for s in (0, 1):
    k = oof_shield == s
    sh.append({"shield": "Y" if s else "N", "orders": int(k.sum()), "return_rate": round(oof_y[k].mean(), 3),
               "share_of_all_returns": round(oof_y[k].sum() / oof_y.sum(), 3),
               "auc_within_group": round(roc_auc_score(oof_y[k], oof_p[k]), 3),
               "share_called": round((oof_p[k] >= km.CALL_THRESHOLD).mean(), 3)})
pd.DataFrame(sh).to_csv(f"{EV}/shield_split.csv", index=False)

# ---- 4. Final model on all clean rows -> model.json, predictions.csv ----
final = lr().fit(X, y)
model = {"coef": dict(zip(cols, map(float, final.coef_[0]))), "intercept": float(final.intercept_[0]),
         "means": dict(zip(cols, map(float, X.mean()))), "trained_rows": int(len(X)),
         "trained_through": tr.order_placed_at.max(), "type": "logistic_regression"}
with open(os.path.join(km.HERE, "model.json"), "w") as f:
    json.dump(model, f, indent=1)
pte = final.predict_proba(Xte)[:, 1]
sub = pd.DataFrame({"order_id": te.order_id, "score": np.round(pte, 6)})
ss = pd.read_csv(f"{D}/sample_submission.csv")
assert list(sub.order_id) == list(ss.order_id) and sub.score.between(0, 1).all()
sub.to_csv(os.path.join(km.HERE, "predictions.csv"), index=False)
te_sh = Xte.shield.values == 1
log["test_rows"] = len(te)
log["test_mean_score"] = round(float(pte.mean()), 4)
log["test_share_above_call_threshold"] = round(float((pte >= km.CALL_THRESHOLD).mean()), 3)
log["test_calls_per_quarter"] = int((pte >= km.CALL_THRESHOLD).sum())
log["test_expected_net_saving_rs_quarter"] = int(((pte * km.CALL_PREVENTS * km.COST_RETURN - km.COST_CALL)
                                                  * (pte >= km.CALL_THRESHOLD)).sum())
log["test_shield_share"] = round(float(te_sh.mean()), 3)
log["call_threshold"] = round(km.CALL_THRESHOLD, 4)
log["coefficients"] = {k: round(v, 3) for k, v in model["coef"].items()}
with open(f"{EV}/data_audit_and_summary.json", "w") as f:
    json.dump(log, f, indent=1, default=str)

# ---- 5. Charts ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
NAVY, BLUE, GREY, RED = "#0A1E3F", "#0082F0", "#9AA5B1", "#E5484D"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(1, 3, figsize=(15, 4.3), facecolor="white")
ax[0].bar(range(len(cal)), cal.actual, color=BLUE, label="actual return rate")
ax[0].plot(range(len(cal)), cal.predicted, "o-", color=NAVY, label="model said")
ax[0].axhline(km.CALL_THRESHOLD, ls="--", color=RED, lw=1); ax[0].text(0, km.CALL_THRESHOLD + .01, "call pays above this", color=RED, fontsize=8)
ax[0].set_title("Out-of-time: risk deciles (low -> high)"); ax[0].set_xlabel("decile"); ax[0].legend(frameon=False, fontsize=8)
sw = pd.DataFrame(sweep)
ax[1].plot(sw.flagged_share, sw.accuracy, "o-", color=NAVY, label="accuracy")
ax[1].axhline(1 - oof_y.mean(), ls=":", color=GREY); ax[1].text(.3, 1 - oof_y.mean() + .005, "flag nothing = %.1f%%" % (100 * (1 - oof_y.mean())), color=GREY, fontsize=8)
ax[1].axhline(.95, ls="--", color=RED); ax[1].text(.3, .952, "95% promise", color=RED, fontsize=8)
ax[1].set_ylim(.4, 1); ax[1].set_title("Accuracy vs share of orders flagged"); ax[1].set_xlabel("share flagged")
ax[2].plot(sw.threshold, sw.CALL_net_rs_per_1000, "o-", color=BLUE)
ax[2].axvline(km.CALL_THRESHOLD, ls="--", color=RED, lw=1)
ax[2].set_title("Call policy: net Rs saved per 1,000 orders"); ax[2].set_xlabel("call if risk >=")
plt.tight_layout(); plt.savefig(f"{EV}/evidence.png", dpi=130)
print(bt.to_string(index=False)); print(json.dumps(log, indent=1, default=str)[:2500])
print(pd.DataFrame(sweep).to_string(index=False)); print(cal); print(pd.DataFrame(sh))
