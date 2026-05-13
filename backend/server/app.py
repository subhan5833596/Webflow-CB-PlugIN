"""
Webflow ↔ CentreBlock Add-on — Flask server.

Architecture:

  ┌────────────────────────────┐         ┌────────────────────────────┐
  │ Webflow Designer App       │ HTTPS   │ Flask Server (this file)   │
  │ (iframe inside Designer)   │ ──────► │                            │
  │ /api/sites, /api/rules     │         │  - manages site creds      │
  └────────────────────────────┘         │  - stores rules            │
                                         │  - holds CB secret         │
  ┌────────────────────────────┐         │  - talks to CentreBlock    │
  │ Published Webflow site     │ HTTPS   │                            │
  │ beacon.js (dumb)           │ ──────► │  /beacon endpoint          │
  │ POST /api/beacon           │         └────────────┬───────────────┘
  └────────────────────────────┘                      │
                                                      ▼
                                              ┌────────────────┐
                                              │ CentreBlock    │
                                              │ prod API       │
                                              └────────────────┘

The browser NEVER receives:
  - the CB customer secret
  - CB API URLs
  - the list of all variables
  - rule definitions
"""

import os
import uuid
import json
import secrets as _secrets
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from flask import Flask, request, jsonify, send_from_directory, redirect, abort
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests as http

import centreblock as cb
import storage


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

WEBFLOW_CLIENT_ID     = os.environ.get("WEBFLOW_CLIENT_ID", "")
WEBFLOW_CLIENT_SECRET = os.environ.get("WEBFLOW_CLIENT_SECRET", "")
WEBFLOW_REDIRECT_URI  = os.environ.get("WEBFLOW_REDIRECT_URI", "http://localhost:5000/oauth/callback")
APP_BASE_URL          = os.environ.get("APP_BASE_URL", "http://localhost:5000")

# Optional: lock down /api/sites and /api/rules to an admin token.
# If unset, those endpoints are open (fine for local dev, NOT for production).
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# CORS:
#  - /api/beacon must be open to any origin (published Webflow sites)
#  - /api/sites and /api/rules are intended for the Designer App iframe;
#    open CORS but they're gated by ADMIN_TOKEN when set.
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)


@app.after_request
def add_no_cache(response):
    if request.path.endswith(".js") or request.path.endswith(".css"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def _require_admin():
    """Gate admin endpoints. No-op if ADMIN_TOKEN unset (dev mode)."""
    if not ADMIN_TOKEN:
        return None
    auth = request.headers.get("Authorization", "")
    expected = f"Bearer {ADMIN_TOKEN}"
    if not _secrets.compare_digest(auth, expected):
        return jsonify({"error": "unauthorized"}), 401
    return None


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.route("/")
def root():
    return jsonify({
        "service": "webflow-centreblock-addon",
        "status": "ok",
        "endpoints": {
            "designer_app": "/app",
            "beacon_script": "/beacon.js",
            "beacon_post": "/api/beacon",
            "sites": "/api/sites",
            "rules": "/api/rules",
        },
    })


# ─────────────────────────────────────────────
# Webflow OAuth (for the Designer App)
# Only needed if you want to use Webflow's Data API
# to read site pages / collections server-side.
# ─────────────────────────────────────────────

@app.route("/oauth/authorize")
def oauth_authorize():
    """Redirect the user to Webflow to grant access to their site."""
    if not WEBFLOW_CLIENT_ID:
        return jsonify({"error": "WEBFLOW_CLIENT_ID not configured"}), 500
    state = _secrets.token_urlsafe(16)
    url = (
        "https://webflow.com/oauth/authorize"
        f"?client_id={WEBFLOW_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={WEBFLOW_REDIRECT_URI}"
        f"&scope=sites:read pages:read"
        f"&state={state}"
    )
    return redirect(url)


@app.route("/oauth/callback")
def oauth_callback():
    """Exchange Webflow auth code for an access token."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing code"}), 400
    if not (WEBFLOW_CLIENT_ID and WEBFLOW_CLIENT_SECRET):
        return jsonify({"error": "OAuth not configured"}), 500
    resp = http.post(
        "https://api.webflow.com/oauth/access_token",
        data={
            "client_id": WEBFLOW_CLIENT_ID,
            "client_secret": WEBFLOW_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": WEBFLOW_REDIRECT_URI,
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return jsonify({"error": "token exchange failed", "details": resp.text}), 502
    # In a real deployment you'd associate this token with the user/site
    # record. For now we just return it to the Designer App via redirect.
    token = resp.json().get("access_token", "")
    return redirect(f"{APP_BASE_URL}/app?wf_token={token}")


# ─────────────────────────────────────────────
# Designer App (iframe) — static files
# ─────────────────────────────────────────────

@app.route("/app")
@app.route("/app/<path:subpath>")
def designer_app(subpath="index.html"):
    base = os.path.join(os.path.dirname(__file__), "..", "designer_app")
    return send_from_directory(base, subpath)


# Serve beacon.js from /beacon.js for clean URL on Webflow Custom Code
@app.route("/beacon.js")
def beacon_js():
    base = os.path.join(os.path.dirname(__file__), "..", "beacon")
    return send_from_directory(base, "beacon.js", mimetype="application/javascript")


# ─────────────────────────────────────────────
# Site CRUD — used by the Designer App
# CB secret is WRITE-ONLY here; never read back to browser.
# ─────────────────────────────────────────────

@app.route("/api/sites", methods=["GET"])
def api_sites_list():
    err = _require_admin()
    if err:
        return err
    return jsonify(storage.list_sites())


@app.route("/api/sites", methods=["POST"])
def api_sites_create():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}

    # Validation
    if not data.get("origin"):
        return jsonify({"error": "origin is required (e.g. https://mysite.webflow.io)"}), 400
    if not data.get("cb_customer_id"):
        return jsonify({"error": "cb_customer_id is required"}), 400
    if not data.get("cb_secret"):
        return jsonify({"error": "cb_secret is required"}), 400

    try:
        cust_id = int(data["cb_customer_id"])
    except (TypeError, ValueError):
        return jsonify({"error": "cb_customer_id must be an integer"}), 400

    # Verify the credentials work by making a real CB call before saving.
    # We attempt to create-or-get a probe consumer; if it fails, the creds
    # are invalid and we reject the save.
    try:
        cb.get_or_create_consumer(
            customer_id=cust_id,
            secret=data["cb_secret"],
            uuid=f"probe_{uuid.uuid4().hex[:8]}",
            audiences=["default"],
        )
    except Exception as e:
        return jsonify({
            "error": "CentreBlock credentials rejected",
            "details": str(e),
        }), 400

    rec = storage.upsert_site(
        name=data.get("name", ""),
        webflow_site_id=data.get("webflow_site_id", ""),
        origin=data["origin"],
        cb_customer_id=cust_id,
        cb_secret=data["cb_secret"],
    )
    return jsonify(rec), 201


@app.route("/api/sites/<site_id>", methods=["GET"])
def api_sites_get(site_id):
    err = _require_admin()
    if err:
        return err
    rec = storage.get_site(site_id)
    if not rec:
        return jsonify({"error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/sites/<site_id>", methods=["PATCH"])
def api_sites_update(site_id):
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    if not storage.get_site(site_id):
        return jsonify({"error": "not found"}), 404

    # If new credentials are provided, verify before saving.
    new_cust = data.get("cb_customer_id")
    new_secret = data.get("cb_secret")
    if new_cust is not None and new_secret:
        try:
            cb.get_or_create_consumer(
                customer_id=int(new_cust),
                secret=new_secret,
                uuid=f"probe_{uuid.uuid4().hex[:8]}",
                audiences=["default"],
            )
        except Exception as e:
            return jsonify({
                "error": "CentreBlock credentials rejected",
                "details": str(e),
            }), 400

    rec = storage.upsert_site(
        site_id=site_id,
        name=data.get("name") or "",
        webflow_site_id=data.get("webflow_site_id") or "",
        origin=data.get("origin") or "",
        cb_customer_id=int(new_cust) if new_cust is not None else None,
        cb_secret=new_secret,
    )
    return jsonify(rec)


@app.route("/api/sites/<site_id>", methods=["DELETE"])
def api_sites_delete(site_id):
    err = _require_admin()
    if err:
        return err
    if not storage.delete_site(site_id):
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": site_id})


# ─────────────────────────────────────────────
# Site discovery — scrape pages & elements
# (same as before, helps the Designer App build a rule)
# ─────────────────────────────────────────────

def _scrape_pages(site_url: str) -> list[dict]:
    res = http.get(site_url, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    base_domain = urlparse(site_url).netloc
    seen, pages = set(), []

    def add(a):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or "mailto:" in href or href.startswith("javascript:"):
            return
        full = urljoin(site_url, href)
        parsed = urlparse(full)
        if parsed.netloc != base_domain or full in seen:
            return
        seen.add(full)
        path = parsed.path.strip("/")
        slug = path.split("/")[-1] if path else ""
        label = slug or a.get_text(strip=True)[:40] or "home"
        pages.append({"label": label, "url": full})

    for tag in soup.find_all(["nav", "header", "footer"]):
        for a in tag.find_all("a", href=True):
            add(a)
    for a in soup.find_all("a", href=True):
        add(a)
    return pages


def _scrape_elements(page_url: str) -> list[dict]:
    res = http.get(page_url, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    allowed = ["a", "button", "input"]
    all_tags = soup.find_all(allowed)
    out = []
    for idx, tag in enumerate(all_tags):
        text = tag.get_text(strip=True)[:60]
        classes = " ".join(tag.get("class", []))
        el_id = tag.get("id", "")
        href = tag.get("href", "") if tag.name == "a" else ""
        if not text and not el_id and not classes and not href:
            continue
        if el_id:
            selector = f"#{el_id}"
        else:
            first_class = classes.split()[0] if classes else ""
            same_before = sum(1 for t in all_tags[:idx] if t.name == tag.name)
            if first_class:
                selector = f"{tag.name}.{first_class}:nth-of-type({same_before + 1})"
            else:
                selector = f"{tag.name}:nth-of-type({same_before + 1})"
        out.append({
            "tag": tag.name, "text": text, "id": el_id,
            "classes": classes, "selector": selector, "href": href, "index": idx,
        })
    return out


@app.route("/api/discover/pages")
def api_discover_pages():
    err = _require_admin()
    if err:
        return err
    site_url = (request.args.get("site_url") or "").strip()
    if not site_url:
        return jsonify({"error": "site_url required"}), 400
    try:
        return jsonify(_scrape_pages(site_url))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/discover/elements")
def api_discover_elements():
    err = _require_admin()
    if err:
        return err
    page_url = (request.args.get("page_url") or "").strip()
    if not page_url:
        return jsonify({"error": "page_url required"}), 400
    try:
        return jsonify(_scrape_elements(page_url))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# Rules CRUD
# Creating a rule also creates the CB variable server-side.
# ─────────────────────────────────────────────

def _suggest_variable_name(element_text: str, page_url: str, site_name: str) -> str:
    import re
    parsed = urlparse(page_url)
    path = parsed.path.strip("/")
    slug = path.split("/")[-1] if path else "home"
    if not slug or slug.lower().startswith("index"):
        slug = "home"
    slug = re.sub(r"[^a-z0-9]", "_", slug.lower()).strip("_") or "home"
    site = re.sub(r"[^a-z]", "_", (site_name or "site").lower()).strip("_") or "site"
    hint = re.sub(r"[^a-z0-9]", "_", (element_text or "el").lower()).strip("_")[:25] or "el"
    parts = [site]
    if slug != site:
        parts.append(slug)
    if hint not in parts:
        parts.append(hint)
    name = re.sub(r"_+", "_", "_".join(parts)).strip("_")
    return name or "variable"


@app.route("/api/rules", methods=["GET"])
def api_rules_list():
    err = _require_admin()
    if err:
        return err
    site_id = request.args.get("site_id")
    return jsonify(storage.list_rules(site_id))


@app.route("/api/rules", methods=["POST"])
def api_rules_create():
    err = _require_admin()
    if err:
        return err
    data = request.get_json() or {}
    site_id = data.get("site_id")
    if not site_id:
        return jsonify({"error": "site_id is required"}), 400

    site = storage.get_site(site_id, with_secret=True)
    if not site:
        return jsonify({"error": "site not found"}), 404
    if not (site.get("cb_customer_id") and site.get("cb_secret")):
        return jsonify({"error": "site has no CB credentials configured"}), 400

    selector = (data.get("selector") or "").strip()
    if not selector:
        return jsonify({"error": "selector is required"}), 400

    # Auto-suggest variable name if not provided
    var_name = (data.get("cb_variable_name") or "").strip()
    if not var_name:
        var_name = _suggest_variable_name(
            data.get("element_text", ""),
            data.get("page_url", ""),
            site.get("name") or urlparse(site.get("origin", "")).netloc.split(".")[0],
        )

    # Create CB variable (skipped if already exists)
    cb_result = {}
    cb_error = None
    try:
        cb_result = cb.create_variable(
            customer_id=site["cb_customer_id"],
            secret=site["cb_secret"],
            name=var_name,
            weight_for_customer=float(data.get("weight_customer", 15)),
            weight_for_default=float(data.get("weight_default", 15)),
            direction=data.get("direction", "Positive"),
            leaving_link=data.get("leaving_link", ""),
            label=data.get("element_text", var_name),
        )
        # CB may have cleaned/normalized the name — use the canonical version
        var_name = cb_result.get("name", var_name)
    except Exception as e:
        cb_error = str(e)

    rule = storage.add_rule({
        "site_id": site_id,
        "page_url": data.get("page_url", ""),
        "selector": selector,
        "action": data.get("action", "click"),
        "element_text": data.get("element_text", ""),
        "element_tag": data.get("element_tag", ""),
        "element_id": data.get("element_id", ""),
        "element_classes": data.get("element_classes", ""),
        "cb_variable_name": var_name,
        "direction": data.get("direction", "Positive"),
    })

    return jsonify({"rule": rule, "cb_result": cb_result, "cb_error": cb_error}), 201


@app.route("/api/rules/<rule_id>", methods=["DELETE"])
def api_rules_delete(rule_id):
    err = _require_admin()
    if err:
        return err
    if not storage.delete_rule(rule_id):
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": rule_id})


# ─────────────────────────────────────────────
# THE BEACON ENDPOINT
# Called by beacon.js on every click on the published Webflow site.
# This is the only endpoint the public-facing browser script talks to.
#
# The beacon sends ONLY: { selector, page_url, visitor_id }
# The server does EVERYTHING ELSE:
#   - identify which site the click belongs to (by Origin header)
#   - look up that site's CB credentials (server-side)
#   - find a matching rule
#   - get/create a CB consumer token for this visitor
#   - fire the CB trigger
# The browser never sees CB URLs, secrets, variable names, or rules.
# ─────────────────────────────────────────────

# Tiny in-process cache of visitor_id -> {site_id -> consumer_token} so we don't
# hit the CB consumer endpoint on every click for the same visitor.
_token_cache: dict[tuple[str, str], str] = {}


@app.route("/api/beacon", methods=["POST", "OPTIONS"])
def api_beacon():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    selector   = (data.get("selector")   or "").strip()
    page_url   = (data.get("page_url")   or "").strip()
    visitor_id = (data.get("visitor_id") or "").strip()

    if not selector:
        return jsonify({"ok": False, "reason": "missing_selector"}), 400

    # Identify the site by the Origin header (set by every browser fetch).
    origin = request.headers.get("Origin", "")
    if not origin:
        # Fallback: derive origin from the page_url the beacon sent.
        parsed = urlparse(page_url)
        if parsed.scheme and parsed.netloc:
            origin = f"{parsed.scheme}://{parsed.netloc}"

    site = storage.find_site_by_origin(origin)
    if not site:
        # Unknown site — accept silently so we don't leak which sites exist
        return jsonify({"ok": True, "matched": False})

    # Find matching rule(s)
    rules = storage.find_matching_rules(site["site_id"], page_url, selector)
    if not rules:
        return jsonify({"ok": True, "matched": False})

    # Get or create a CB consumer token for this visitor (cached)
    if not visitor_id:
        visitor_id = request.remote_addr or f"anon_{uuid.uuid4().hex[:8]}"
    cache_key = (site["site_id"], visitor_id)
    consumer_token = _token_cache.get(cache_key)

    if not consumer_token:
        try:
            result = cb.get_or_create_consumer(
                customer_id=site["cb_customer_id"],
                secret=site["cb_secret"],
                uuid=visitor_id,
                audiences=["default"],
                tags={"entry_page": page_url[:60]},
            )
            consumer_token = result.get("data") or result.get("token") or ""
            if consumer_token:
                _token_cache[cache_key] = consumer_token
        except Exception as e:
            return jsonify({"ok": False, "reason": "consumer_failed", "detail": str(e)}), 200

    # Fire trigger(s)
    fired = []
    for rule in rules:
        var_name = rule.get("cb_variable_name", "")
        if not var_name:
            continue
        try:
            cb.fire_trigger(
                variable_name=var_name,
                consumer_token=consumer_token,
                page=page_url,
                direction=rule.get("direction", "Neutral"),
            )
            fired.append(var_name)
        except Exception as e:
            print(f"[beacon] trigger {var_name} failed: {e}")

    # Response is intentionally minimal — no variable names, no site info.
    return jsonify({"ok": True, "matched": len(fired) > 0})


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
