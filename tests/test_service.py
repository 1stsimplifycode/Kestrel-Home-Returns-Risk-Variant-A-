"""Standard-library tests. Run: python -m unittest discover -s tests"""
import json, os, sys, threading, unittest, urllib.request, urllib.error, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kestrel_model as km
import serve

BASE = {"order_id": "T1", "order_placed_at": "2026-09-20 14:10", "sku": "KH-RV-02", "qty": 1,
        "payment_mode": "cod", "sales_channel": "marketplace", "discount_pct": 20,
        "promised_delivery_days": 8, "customer_prior_orders": 2, "customer_prior_returns": 1,
        "is_gift": "N", "shield_member": "N", "delivery_pincode": "411001", "signup_date": "2024-06-01"}


class TestModel(unittest.TestCase):
    def setUp(self):
        self.s = km.Scorer()

    def test_risky_order_gets_call(self):
        out = self.s.explain(BASE)
        self.assertGreater(out["return_probability"], km.CALL_THRESHOLD)
        self.assertEqual(out["recommended_action"], "CALL BEFORE DISPATCH")
        self.assertFalse(out["hold_dispatch"])
        self.assertIn("Cash on delivery", out["raises_risk"])

    def test_safe_order_ships(self):
        r = dict(BASE, payment_mode="prepaid_upi", customer_prior_returns=0, discount_pct=0,
                 sku="KH-MG-01", promised_delivery_days=3, sales_channel="partner_outlet")
        self.assertEqual(self.s.explain(r)["recommended_action"], "SHIP NORMALLY")

    def test_more_prior_returns_more_risk(self):
        p0 = self.s.score(dict(BASE, customer_prior_returns=0))[0]
        p3 = self.s.score(dict(BASE, customer_prior_returns=3))[0]
        self.assertLess(p0, p3)

    def test_unknown_sku_rejected(self):
        with self.assertRaises(ValueError):
            self.s.score(dict(BASE, sku="NOPE"))

    def test_missing_optional_fields_ok(self):
        p, _ = self.s.score({"sku": "KH-AF-01", "payment_mode": "cod", "sales_channel": "app"})
        self.assertTrue(0 < p < 1)

    def test_predictions_file_shape(self):
        root = os.path.dirname(km.HERE + "/x")
        with open(os.path.join(root, "predictions.csv")) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2096)
        self.assertEqual(len({r["order_id"] for r in rows}), 2096)
        self.assertTrue(all(0 <= float(r["score"]) <= 1 for r in rows))


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.H)
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, body):
        req = urllib.request.Request(self.url + "/score", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_score_ok(self):
        code, j = self.post(json.dumps(BASE).encode())
        self.assertEqual(code, 200)
        self.assertIn("raises_risk", j)

    def test_bad_json_400(self):
        self.assertEqual(self.post(b"{not json")[0], 400)

    def test_missing_field_400(self):
        self.assertEqual(self.post(json.dumps({"sku": "KH-AF-01"}).encode())[0], 400)

    def test_page(self):
        with urllib.request.urlopen(self.url + "/") as r:
            self.assertIn(b"Dispatch check", r.read())


if __name__ == "__main__":
    unittest.main()
