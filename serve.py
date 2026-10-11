"""Returns-risk service. Standard library only - no pip install, no API key.
  python serve.py            -> http://127.0.0.1:8000
  POST /score  {order JSON}  -> score + reasons + recommended action
  GET  /health
"""
import json, os, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import kestrel_model as km

SCORER = km.Scorer()
PAGE = open(os.path.join(km.HERE, "static", "index.html"), "rb").read()
REQUIRED = ["sku", "payment_mode", "sales_channel"]


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/health":
            return self._send(200, {"status": "ok", "model": "logistic_regression",
                                    "call_threshold": round(km.CALL_THRESHOLD, 4)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/score":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 20000:
                return self._send(413, {"error": "record too large"})
            rec = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(rec, dict):
                raise ValueError("send one JSON object (a single order)")
            missing = [k for k in REQUIRED if not rec.get(k)]
            if missing:
                return self._send(400, {"error": "missing fields: " + ", ".join(missing)})
            out = SCORER.explain(rec)
            out["order_id"] = rec.get("order_id")
            self._send(200, out)
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # never crash the server on one bad record
            self._send(500, {"error": "could not score this record: %s" % e})

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + fmt % args + "\n")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    print(f"Kestrel returns-risk service on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
