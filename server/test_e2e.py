"""
End-to-end test with CentreBlock mocked at the requests library level.
Verifies the full Flask pipeline: site save → rule create → beacon fire →
CB calls dispatched with correct args.
"""
import json, os, sys, shutil
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
if os.path.exists(DATA_DIR):
    shutil.rmtree(DATA_DIR)

import app as app_module
client = app_module.app.test_client()

cb_calls = []

def fake_cb_post(url, json=None, headers=None, timeout=None, **kwargs):
    cb_calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
    resp = MagicMock()
    resp.status_code = 200
    if "/consumer" in url:
        resp.json.return_value = {"status": "success", "data": "consumer_token_abc123"}
    elif "/variables/" in url:
        resp.json.return_value = {"status": "success", "id": "var_xyz"}
    elif "/trigger/" in url:
        resp.status_code = 201
        resp.json.return_value = {"status": "ok"}
    else:
        resp.json.return_value = {}
    resp.text = json_dumps(resp.json.return_value)
    resp.raise_for_status = lambda: None
    return resp

def json_dumps(o): return __import__("json").dumps(o)

def fake_cb_get(url, headers=None, timeout=None, **kwargs):
    cb_calls.append({"method": "GET", "url": url, "headers": headers})
    resp = MagicMock()
    resp.status_code = 200
    if "/csv/" in url:
        resp.text = "name,category,weight\n"  # empty → variable will be created
    else:
        resp.text = "{}"
        resp.json.return_value = {}
    resp.raise_for_status = lambda: None
    return resp

with patch("centreblock.requests.post", side_effect=fake_cb_post), \
     patch("centreblock.requests.get",  side_effect=fake_cb_get):

    CB_CUSTOMER_ID = 117
    CB_SECRET = "test_secret_xyz=="
    ORIGIN = "https://e2e-test-site.example.com"
    PAGE = ORIGIN + "/test-page"
    SELECTOR = "#cta-button"

    print("══ 1. Register site (CB creds verified via mocked /consumer) ══")
    r = client.post("/api/sites", json={
        "name": "E2E test site", "origin": ORIGIN,
        "cb_customer_id": CB_CUSTOMER_ID, "cb_secret": CB_SECRET,
    })
    body = r.get_json()
    assert r.status_code == 201, body
    site_id = body["site_id"]
    assert "cb_secret" not in body
    print("  ✓ Site created, secret NOT in response")
    assert any("/consumer" in c["url"] for c in cb_calls)
    print("  ✓ CB /consumer was called to verify creds")

    print("\n══ 2. Secret encrypted on disk ══")
    with open(os.path.join(DATA_DIR, "sites.json")) as f:
        on_disk = f.read()
    assert CB_SECRET not in on_disk, "PLAINTEXT SECRET ON DISK!"
    print(f"  ✓ Plaintext secret NOT in sites.json ({len(on_disk)} bytes on disk)")

    print("\n══ 3. Create rule → mocked CB variable create ══")
    cb_calls.clear()
    r = client.post("/api/rules", json={
        "site_id": site_id, "page_url": PAGE, "selector": SELECTOR,
        "action": "click", "element_text": "Get Started",
        "element_tag": "a", "direction": "Positive",
    })
    body = r.get_json()
    assert r.status_code == 201
    var_name = body["rule"]["cb_variable_name"]
    print(f"  ✓ rule.cb_variable_name = {var_name}")
    var_post = [c for c in cb_calls if c["method"] == "POST" and "/variables/" in c["url"]]
    assert len(var_post) == 1
    payload_sent = var_post[0]["json"]
    assert payload_sent["name"] == var_name
    print(f"  ✓ CB /variables called with name={payload_sent['name']}")

    print("\n══ 4. Fire beacon → consumer + trigger ══")
    cb_calls.clear()
    r = client.post(
        "/api/beacon",
        json={"selector": SELECTOR, "page_url": PAGE, "visitor_id": "visitor_001"},
        headers={"Origin": ORIGIN},
    )
    body = r.get_json()
    assert r.status_code == 200 and body == {"ok": True, "matched": True}
    consumer_calls = [c for c in cb_calls if "/consumer" in c["url"]]
    trigger_calls = [c for c in cb_calls if "/trigger/" in c["url"]]
    assert len(consumer_calls) == 1 and len(trigger_calls) == 1
    assert var_name in trigger_calls[0]["url"]
    trigger_hdrs = trigger_calls[0]["headers"]
    assert trigger_hdrs.get("x-centreblock-consumer-token") == "consumer_token_abc123"
    assert "x-centreblock-token" not in trigger_hdrs
    print(f"  ✓ Trigger fired at .../trigger/{var_name}")
    print(f"  ✓ Trigger used consumer-token header (not the customer secret)")

    print("\n══ 5. Second beacon → token cache hit ══")
    cb_calls.clear()
    r = client.post(
        "/api/beacon",
        json={"selector": SELECTOR, "page_url": PAGE, "visitor_id": "visitor_001"},
        headers={"Origin": ORIGIN},
    )
    assert r.status_code == 200
    consumer_calls = [c for c in cb_calls if "/consumer" in c["url"]]
    trigger_calls = [c for c in cb_calls if "/trigger/" in c["url"]]
    assert len(consumer_calls) == 0 and len(trigger_calls) == 1
    print("  ✓ Cached token: 0 consumer calls, 1 trigger call")

    print("\n══ 6. Beacon from unknown origin ══")
    cb_calls.clear()
    r = client.post(
        "/api/beacon",
        json={"selector": SELECTOR, "page_url": PAGE, "visitor_id": "v"},
        headers={"Origin": "https://attacker.example"},
    )
    assert r.get_json() == {"ok": True, "matched": False}
    assert len(cb_calls) == 0
    print("  ✓ Unknown origin → silent 200, zero CB calls")

    print("\n══ 7. Beacon, non-matching selector ══")
    cb_calls.clear()
    r = client.post(
        "/api/beacon",
        json={"selector": "#nothing", "page_url": PAGE, "visitor_id": "v"},
        headers={"Origin": ORIGIN},
    )
    assert r.get_json() == {"ok": True, "matched": False}
    assert not [c for c in cb_calls if "/trigger/" in c["url"]]
    print("  ✓ Non-matching selector → no trigger fired")

    print("\n══ 8. Designer App index does NOT contain the secret ══")
    r = client.get("/app")
    assert CB_SECRET not in r.get_data(as_text=True)
    print("  ✓ Designer App index does not embed the secret")

    print("\n══ 9. beacon.js does NOT contain CB URL or secret ══")
    js = client.get("/beacon.js").get_data(as_text=True)
    assert "centreblock.net" not in js
    assert "x-centreblock" not in js
    assert CB_SECRET not in js
    print(f"  ✓ beacon.js ({len(js)} bytes) has no CB URL, header, or secret")

    print("\n══ 10. ADMIN_TOKEN gate ══")
    app_module.ADMIN_TOKEN = "super_secret_admin"
    assert client.get("/api/sites").status_code == 401
    assert client.get(
        "/api/sites", headers={"Authorization": "Bearer super_secret_admin"}
    ).status_code == 200
    print("  ✓ Without ADMIN_TOKEN: 401; With ADMIN_TOKEN: 200")
    app_module.ADMIN_TOKEN = ""

    print("\n\n🎉 ALL END-TO-END TESTS PASSED")
