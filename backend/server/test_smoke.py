"""
Smoke-test the Flask app entirely in-process via the WSGI test client.
This bypasses the need to keep a server running across tool calls.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# Clean any existing data dir state
import shutil
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if os.path.exists(DATA_DIR):
    shutil.rmtree(DATA_DIR)

import app as app_module
client = app_module.app.test_client()

def show(label, resp):
    body = resp.get_data(as_text=True)
    try:
        body = json.dumps(json.loads(body), indent=2)
    except Exception:
        pass
    print(f"\n── {label} ── [{resp.status_code}]")
    print(body[:800])

# 1. Root health
show("GET /", client.get("/"))

# 2. List sites (empty)
show("GET /api/sites (empty)", client.get("/api/sites"))

# 3. POST site with missing origin
show("POST /api/sites (missing origin)",
     client.post("/api/sites", json={"cb_customer_id": 1, "cb_secret": "x"}))

# 4. POST site with missing cb_customer_id
show("POST /api/sites (missing cb_customer_id)",
     client.post("/api/sites", json={"origin": "https://x.example", "cb_secret": "x"}))

# 5. POST site with non-int customer id
show("POST /api/sites (non-int customer id)",
     client.post("/api/sites", json={"origin": "https://x.example",
                                     "cb_customer_id": "abc", "cb_secret": "x"}))

# 6. POST site with bogus creds (CB will reject) — this hits CB live.
#    We expect 400 with a CB-rejected error. Skip if no internet.
show("POST /api/sites (bogus CB creds, hits live CB)",
     client.post("/api/sites", json={
         "origin": "https://probe-test-site-9999.example",
         "name": "probe",
         "cb_customer_id": 999999,
         "cb_secret": "bogus_secret_value",
     }))

# 7. Beacon with no Origin header → unknown site → silent 200 with matched=false
show("POST /api/beacon (no origin, unknown site)",
     client.post("/api/beacon", json={"selector": "#test", "page_url": "https://x.example/p"}))

# 8. Beacon with empty selector → 400
show("POST /api/beacon (empty selector)",
     client.post("/api/beacon", json={"selector": "", "page_url": "https://x.example/p"}))

# 9. Designer App index serves
r = client.get("/app")
print(f"\n── GET /app ── [{r.status_code}]")
print("Content-Type:", r.content_type)
print("First 200 chars:", r.get_data(as_text=True)[:200])

# 10. beacon.js serves
r = client.get("/beacon.js")
print(f"\n── GET /beacon.js ── [{r.status_code}]")
print("Content-Type:", r.content_type)
print("First 200 chars:", r.get_data(as_text=True)[:200])

# 11. List rules without site_id
show("GET /api/rules (no filter)", client.get("/api/rules"))

# 12. POST rule referencing non-existent site
show("POST /api/rules (unknown site)",
     client.post("/api/rules", json={"site_id": "does-not-exist", "selector": "#x"}))

print("\n\nAll smoke tests complete.")
