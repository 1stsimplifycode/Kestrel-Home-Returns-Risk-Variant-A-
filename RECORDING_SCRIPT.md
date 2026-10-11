# Screen recording script (≤ 3:00, no slides)

Record with OBS / Windows Game Bar (Win+Alt+R) / macOS (Cmd+Shift+5). Show only the editor, terminal and browser.

| Time | Show on screen | Say |
|---|---|---|
| 0:00–0:20 | `data/email-thread.txt`, then `ops-policy.pdf` §4/§7 | "Ritu asked for 95% accuracy and to hold flagged orders. The policy says a return costs Rs 1,150, a hold loses 12% of customers, a Rs 45 call stops 35% of returns. So this is a money decision, not an accuracy contest." |
| 0:20–0:50 | `evidence/data_audit_and_summary.json` (leak_columns block) | "**What I tried first:** all columns. Pickup-booked rows return 92% of the time, REVERSE_PICKUP 100%. That model hit 99% accuracy. But the dispatch snapshot has zero pickups — those fields are written after the return. **Threw it away.**" |
| 0:50–1:15 | Same file: duplicates, ×100 values; `DECISIONS.md` | "**What I changed:** removed 651 duplicate partner-feed rows, stopped using order value because October 2025 is stored ×100, ignored the free-text notes. 17 decisions are logged here." |
| 1:15–1:40 | `evidence/backtest_by_quarter.csv` + `evidence.png` | "Trained on the past, tested on the next quarter, three times. AUC 0.77 to 0.79, steady. Gradient boosting lost every quarter — **discarded**, kept logistic regression because staff can read its reasons. Middle chart: accuracy never gets near 95%; flagging nothing already scores 89%." |
| 1:40–2:05 | Right chart + `threshold_sweep.csv` | "Calling everyone above 11% risk — the break-even — calls a third of orders, catches 68% of returns, nets about Rs 16,700 per 1,000 orders. Holding at the same level loses 29 good orders per 1,000. **Changed the action from hold to call.**" |
| 2:05–2:40 | Double-click `run.bat` → browser → score a COD robot vacuum with 1 prior return, then switch to UPI / 0 returns | "Standard library only, starts with no installs or keys. High risk → call, with reasons. Prepaid, no history → ship. It never recommends a hold." |
| 2:40–3:00 | `MEMO.md` "next week" | "Next week: a two-week randomised call test, because the 35% comes from one pilot. Expected hidden-set AUC: about 0.78." |
