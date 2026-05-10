"""
Webflow CentreBlock Tracker — Flask backend
No database.  All persistent state lives in CentreBlock.
In-memory dicts cache site pages / scraped elements for the current process.
"""

import uuid
import json
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests as http

import centreblock as cb

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

# ──────────────────────────────────────────────
# In-memory stores  (reset on dyno restart — fine for stateless design)
# ──────────────────────────────────────────────

_site_pages: dict[str, list[dict]] = {}    # web_url  → [{label, url}, …]
_page_elements: dict[str, list[dict]] = {} # page_url → [{tag, text, id, classes, selector}, …]
_rules: list[dict] = []                    # tracking rules
_events: list[dict] = []                   # fired trigger log (in-process only)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_selector(tag) -> str | None:
    """
    Simple selector — priority:
    1. #id  (most specific)
    2. tag.first-class  (e.g. a.nav_menu_link)
    3. tag  (fallback)
    """
    try:
        # 1. ID — sabse specific
        if tag.get("id"):
            return f"#{tag['id']}"

        tag_name = tag.name
        classes  = tag.get("class", [])

        # 2. tag + first class
        if classes:
            first_class = classes[0]
            return f"{tag_name}.{first_class}"

        # 3. Sirf tag
        return tag_name
    except Exception:
        return None


def _scrape_pages(site_url: str) -> list[dict]:
    """
    Return deduplicated pages from a site.
    Priority: nav/header/footer links first (most reliable page links),
    then all other internal links.
    Label = slug from URL path (e.g. /about-us -> about-us).
    """
    res = http.get(site_url, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    seen: set[str] = set()
    pages: list[dict] = []
    base_domain = urlparse(site_url).netloc

    def add_link(a_tag):
        href = a_tag.get("href", "").strip()
        if not href or href.startswith("#") or "mailto:" in href or href.startswith("javascript:"):
            return
        full = urljoin(site_url, href)
        parsed = urlparse(full)
        if parsed.netloc != base_domain:
            return
        if full in seen:
            return
        seen.add(full)

        # Label = slug from path (e.g. /about-us -> "about-us"), fallback to link text
        path = parsed.path.strip("/")
        slug = path.split("/")[-1] if path else ""
        label = slug or a_tag.get_text(strip=True)[:40] or "home"
        pages.append({"label": label, "url": full})

    # Priority 1 — nav, header, footer (most reliable navigation links)
    NAV_TAGS = ["nav", "header", "footer" , "base"]
    for container in soup.find_all(NAV_TAGS):
        for a in container.find_all("a", href=True):
            add_link(a)

    # Priority 2 — all other links on page
    for a in soup.find_all("a", href=True):
        add_link(a)

    return pages


def _scrape_elements(page_url: str) -> list[dict]:
    """
    Return all clickable elements — no deduplication.
    Every button/link gets a unique nth-of-type selector.
    EXTENSIBLE: Add more types to ALLOWED_ELEMENT_TYPES as needed.
    """
    res = http.get(page_url, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # EXTENSIBLE: Add more types here as needed e.g. "select", "textarea"
    ALLOWED_ELEMENT_TYPES = ["a", "button", "input"]
    all_tags = soup.find_all(ALLOWED_ELEMENT_TYPES)

    elements: list[dict] = []

    for idx, tag in enumerate(all_tags):
        tag_name = tag.name
        text     = tag.get_text(strip=True)[:60]
        classes  = " ".join(tag.get("class", []))
        el_id    = tag.get("id", "")
        href     = tag.get("href", "") if tag_name == "a" else ""

        # Skip truly empty elements
        if not text and not el_id and not classes and not href:
            continue

        # Build unique selector
        if el_id:
            selector = f"#{el_id}"
        else:
            first_class = classes.split()[0] if classes else ""
            same_before = sum(1 for t in all_tags[:idx] if t.name == tag_name)
            if first_class:
                selector = f"{tag_name}.{first_class}:nth-of-type({same_before + 1})"
            else:
                selector = f"{tag_name}:nth-of-type({same_before + 1})"

        # Parent context — walk up tree until meaningful id or class found
        parent_context = ""
        for parent in tag.parents:
            if parent.name in ["section", "div", "article", "main", "header", "footer", "nav"]:
                parent_id  = parent.get("id", "")
                parent_cls = " ".join(parent.get("class", []))
                if parent_id and parent_id not in ("", "None"):
                    parent_context = parent_id
                    break
                elif parent_cls:
                    # Pick first meaningful class (skip generic ones)
                    skip = {"w-container", "container", "wrapper", "inner", "outer", "row", "col", "div"}
                    cls_parts = parent_cls.split()
                    for c in cls_parts:
                        if c.lower() not in skip and len(c) > 2:
                            parent_context = c
                            break
                    if parent_context:
                        break

        elements.append({
            "tag":      tag_name,
            "text":     text,
            "id":       el_id,
            "classes":  classes,
            "selector": selector,
            "href":     href,
            "context":  parent_context,
            "index":    idx,
        })

    return elements


def _suggest_variable_name(element: dict, page_url: str) -> str:
    """Auto-generate a CentreBlock-safe variable name from element data."""
    import re

    # Website name — domain se nikalo (e.g. "dartmarketing" from "www.dartmarketing.io")
    parsed_url = urlparse(page_url)
    domain     = parsed_url.netloc.replace("www.", "")          # "dartmarketing.io"
    site_name  = domain.split(".")[0]                           # "dartmarketing"
    site_name  = re.sub(r"[^a-z]", "_", site_name.lower()).strip("_") or "site"
    # Number/IP se start na ho — "site" use karo
    if not site_name or not site_name[0].isalpha():
        site_name = "site"

    # Page slug — sirf path ka last part
    path = parsed_url.path.strip("/")
    raw_slug = path.split("/")[-1] if path else "home"
    # index.html, index.php etc -> "home"
    if not raw_slug or raw_slug.lower().startswith("index"):
        raw_slug = "home"
    slug = re.sub(r"[^a-z0-9]", "_", raw_slug.lower()).strip("_") or "home"

    # Element hint — text > id > first class > tag
    raw = (
        element.get("text") or
        element.get("id") or
        element.get("tag") or
        "el"
    )
    hint = re.sub(r"[^a-z0-9]", "_", raw.lower())
    hint = re.sub(r"_+", "_", hint).strip("_")[:25]

    # Build: sitename_slug_hint — duplicates skip karo
    parts = [site_name]
    if slug != site_name:
        parts.append(slug)
    if hint != slug and hint != site_name:
        parts.append(hint)

    # Add context if available (makes same-text buttons unique)
    context = element.get("context", "")
    if context:
        ctx_clean = re.sub(r"[^a-z0-9]", "_", context.lower()).strip("_")[:20]
        if ctx_clean and ctx_clean not in parts:
            parts.append(ctx_clean)

    name = "_".join(parts)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "variable"


# ──────────────────────────────────────────────
# Routes — pages
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("setup.html")


@app.route("/dashboard")
def dashboard():
    return render_template("index.html")


@app.route("/tracking_rule")
def tracking_rule():
    return render_template("tracking_rule.html")


@app.route("/tracking_history")
def tracking_history():
    return render_template("tracking_history.html")


@app.route("/setup_page")
def setup_page():
    return render_template("setup.html")


@app.route("/testing")
def testing():
    return render_template("testing.html")


@app.route("/variables")
def variables():
    return render_template("variables.html")


# ──────────────────────────────────────────────
# Routes — site & element discovery
# ──────────────────────────────────────────────

@app.route("/setup", methods=["POST"])
def setup():
    """Register a website and scrape its pages."""
    data = request.get_json() or {}
    site_url = (data.get("webflow_url") or "").strip()
    if not site_url:
        return jsonify({"error": "Missing webflow_url"}), 400

    # Extract domain only — e.g. "yoursite.webflow.io" from "https://yoursite.webflow.io/page"
    domain = urlparse(site_url).netloc.replace(":", "_")  # "127.0.0.1_5000" or "yoursite.webflow.io"

    if site_url in _site_pages:
        return jsonify({"message": "Website already exists", "pages": _site_pages[site_url]})

    try:
        # Step 1 — Scrape pages
        pages = _scrape_pages(site_url)
        _site_pages[site_url] = pages

        # Step 2 — Register website in CentreBlock using domain as UUID
        result = cb.get_or_create_consumer(
            uuid=domain,              # "yoursite.webflow.io"
            audiences=["default"]
        )
        token = result.get("data", "")
        print(f"CB Consumer Token: {token}")

        # Step 3 — Token milte hi trigger fire karo
        trigger_res = http.post(
            "https://prod.centreblock.net/api/v1/trigger/test/user_added",
            headers={
                "Content-Type": "application/json",
                "x-centreblock-consumer-token": token
            },
            json={}
        )
        print(f"Trigger Response: {trigger_res.status_code} — {trigger_res.text}")

        return jsonify({"message": "Setup saved", "pages": pages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/extract_pages")
def extract_pages():
    """Return cached page list for a site."""
    site_url = request.args.get("site_url", "").strip()
    if not site_url:
        return jsonify({"error": "Missing site_url"}), 400

    if site_url not in _site_pages:
        try:
            _site_pages[site_url] = _scrape_pages(site_url)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify(_site_pages[site_url])


@app.route("/get_elements")
def get_elements():
    """Return (cached) clickable elements for a page."""
    page_url = request.args.get("page_url", "").strip()
    web_url = request.args.get("web_url", "").strip()
    if not page_url:
        return jsonify({"error": "Missing page_url"}), 400

    if page_url in _page_elements:
        return jsonify({"message": "Elements already exist", "elements": _page_elements[page_url]})

    try:
        elements = _scrape_elements(page_url)
        _page_elements[page_url] = elements
        return jsonify({"elements": elements})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Routes — rules
# ──────────────────────────────────────────────

@app.route("/add_rule", methods=["POST"])
def add_rule():
    """
    Add a tracking rule.
    Automatically creates a CentreBlock variable for the element.
    """
    data = request.get_json() or {}

    print("\n" + "="*50)
    print("📋 NEW TRACKING RULE")
    print("="*50)
    print(f"🌐 Website     : {data.get('website_url', '')}")
    print(f"📄 Page        : {data.get('page_url', '')}")
    print(f"🏷️  Tag         : {data.get('element_tag', '')}")
    print(f"📝 Text        : {data.get('element_text', '')}")
    print(f"🆔 ID          : {data.get('element_id', '')}")
    print(f"🎨 Classes     : {data.get('element_classes', '')}")
    print(f"🔍 Selector    : {data.get('selector', '')}")
    print(f"⚙️  Action      : {data.get('action', '')}")
    print(f"➡️  Direction   : {data.get('direction', '')}")
    print(f"⚖️  Weight Cust : {data.get('weight_customer', 15)}")
    print(f"⚖️  Weight Def  : {data.get('weight_default', 15)}")
    print("="*50)

    # Build variable name from element metadata
    element_info = {
        "text": data.get("element_text", ""),
        "id":   data.get("element_id", ""),
        "tag":  data.get("element_tag", ""),
    }
    var_name = data.get("cb_variable_name") or _suggest_variable_name(
        element_info, data.get("page_url", "")
    )
    print(f"🎯 Variable Name : {var_name}")

    # Create variable in CentreBlock
    cb_result = {}
    cb_error = None

    # Agar element ek outbound link hai toh leaving_link tag set karo (whitepaper 6.2)
    element_href = data.get("element_href", "")
    page_url     = data.get("page_url", "")
    website_url  = data.get("website_url", "")
    is_outbound  = (
        element_href.startswith("http") and
        website_url and
        not element_href.startswith(website_url)
    )
    leaving_link = element_href if is_outbound else ""

    try:
        cb_result = cb.create_variable(
            name=var_name,
            weight_for_customer=float(data.get("weight_customer", 15)),
            weight_for_default=float(data.get("weight_default", 15)),
            direction=data.get("direction", "Positive"),
            leaving_link=leaving_link,
            label=data.get("element_text", var_name),
        )
        if cb_result.get("skipped"):
            print(f"Variable '{var_name}' already exists — naya nahi banaya")
        else:
            print(f"Variable '{var_name}' CB mein create hua ✅")
    except Exception as e:
        cb_error = str(e)

    rule = {
        "rule_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "website_url": data.get("website_url", ""),
        "page_url": data.get("page_url", ""),
        "action": data.get("action", "click"),
        "selector": data.get("selector", ""),
        "element_text": data.get("element_text", ""),
        "element_tag": data.get("element_tag", ""),
        "element_id": data.get("element_id", ""),
        "element_classes": data.get("element_classes", ""),
        "cb_variable_name": var_name,
        "direction": data.get("direction", "Positive"),
    }
    _rules.append(rule)

    return jsonify({
        "message": "Rule added",
        "rule": rule,
        "cb_variable": cb_result,
        "cb_error": cb_error,
    })


@app.route("/get_rules")
def get_rules():
    return jsonify(_rules)


@app.route("/delete_rule/<rule_id>", methods=["DELETE"])
def delete_rule(rule_id: str):
    global _rules
    before = len(_rules)
    _rules = [r for r in _rules if r["rule_id"] != rule_id]
    if len(_rules) < before:
        return jsonify({"message": f"Rule {rule_id} deleted"})
    return jsonify({"error": "Rule not found"}), 404


# ──────────────────────────────────────────────
# Routes — consumer token (called by tracker.js)
# ──────────────────────────────────────────────

@app.route("/get_consumer_token", methods=["POST"])
def get_consumer_token():
    """
    Called by tracker.js on page load.
    Accepts: { uuid, entry_page, referer, audiences }
    Returns: { token }
    """
    data = request.get_json() or {}
    visitor_uuid = data.get("uuid") or request.remote_addr or str(uuid.uuid4())

    try:
        result = cb.get_or_create_consumer(
            uuid=visitor_uuid,
            audiences=data.get("audiences", ["default"]),
            tags={
                "entry_page": data.get("entry_page", ""),
                "referer":    data.get("referer", ""),
            },
        )
        token = result.get("data") or result.get("token") or ""
        return jsonify({"token": token, "uuid": visitor_uuid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Routes — event tracking (called by tracker.js on click)
# ──────────────────────────────────────────────

@app.route("/track_event", methods=["POST"])
def track_event():
    """
    Called by tracker.js when a tracked element is clicked.
    Payload: {
        consumer_token,   # CB token for this visitor
        variable_name,    # CB variable name from matching rule
        page_url,
        selector,
        action,
        website_url,
        direction,        # optional
        tags              # optional extra tags
    }
    Fires a CentreBlock trigger and logs the event.
    """
    event = request.get_json() or {}

    consumer_token = event.get("consumer_token", "")
    variable_name  = event.get("variable_name", "")

    cb_result = {}
    cb_error  = None

    if consumer_token and variable_name:
        try:
            cb_result = cb.fire_trigger(
                variable_name=variable_name,
                consumer_token=consumer_token,
                page=event.get("page_url", ""),
                direction=event.get("direction", "Neutral"),
                extra_tags=event.get("tags"),
            )
        except Exception as e:
            cb_error = str(e)

    logged = {
        "id":            str(uuid.uuid4()),
        "timestamp":     event.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "user":          event.get("user", "anonymous"),
        "website_url":   event.get("website_url", ""),
        "page_url":      event.get("page_url", ""),
        "selector":      event.get("selector", ""),
        "action":        event.get("action", ""),
        "variable_name": variable_name,
        "matched_rule":  event.get("matched_rule", False),
        "cb_status":     cb_result.get("status"),
        "cb_error":      cb_error,
    }
    _events.append(logged)

    return jsonify({"status": "ok", "event": logged, "cb_error": cb_error})


@app.route("/get_events")
def get_events():
    return jsonify(_events)


# ──────────────────────────────────────────────
# Routes — CentreBlock variables management
# ──────────────────────────────────────────────

@app.route("/fire_trigger", methods=["POST"])
def fire_trigger_proxy():
    """
    tracker.js se aata hai — CB Trigger API ko proxy karta hai.
    CB URL aur secret browser ko kabhi nahi dikhti.
    """
    data           = request.get_json() or {}
    variable_name  = data.get("variable_name", "").strip()
    consumer_token = data.get("consumer_token", "").strip()
    page           = data.get("page", "")
    direction      = data.get("direction", "Neutral")
    print(f"✅ Trigger: {variable_name} | {consumer_token} | {page} | {direction}")
    if not variable_name or not consumer_token:
        return jsonify({"error": "variable_name aur consumer_token dono chahiye"}), 400

    try:
        result = cb.fire_trigger(
            variable_name=variable_name,
            consumer_token=consumer_token,
            page=page,
            direction=direction,
        )
        print(f"✅ Trigger fired: {variable_name} | status: {result}")
        return jsonify({"status": "ok", "cb_response": result})
    except Exception as e:
        print(f"❌ Trigger error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/cb_variables", methods=["GET"])
def cb_variables():
    """Fetch all variables from CentreBlock as CSV and return as JSON array."""
    try:
        import csv, io
        raw_csv = cb.get_variables_csv()
        print(f"CB Variables RAW CSV:\n{raw_csv[:300]}")

        # csv.DictReader with quotechar fix
        reader = csv.DictReader(io.StringIO(raw_csv), quotechar='"', skipinitialspace=True)
        rows = []
        for row in reader:
            clean = {}
            for k, v in row.items():
                clean_key = k.strip().strip('"').strip() if k else k
                clean_val = v.strip().strip('"').strip() if v else v
                clean[clean_key] = clean_val
            rows.append(clean)

        print(f"CB Variables parsed: {len(rows)} variables")
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/cb_create_variable", methods=["POST"])
def cb_create_variable():
    """Manually create a CentreBlock variable."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Missing variable name"}), 400
    try:
        result = cb.create_variable(
            name=name,
            weight_for_customer=float(data.get("weight_customer", 15)),
            weight_for_default=float(data.get("weight_default", 15)),
            direction=data.get("direction", "Positive"),
            tags=data.get("tags", {}),
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

@app.route("/test_trigger", methods=["GET"])
def test_trigger():
    """
    Direct test — browser mein kholo:
    http://localhost:5000/test_trigger?variable=dartmarketing_home&domain=www.dartmarketing.io
    """
    variable = request.args.get("variable", "").strip()
    domain   = request.args.get("domain", "").strip()

    if not variable or not domain:
        return jsonify({"error": "variable aur domain dono chahiye"}), 400

    try:
        # Step 1 — Consumer token lo
        consumer_result = cb.get_or_create_consumer(
            uuid=domain,
            audiences=["default"],
            tags={"entry_page": "test", "referer": ""}
        )
        token = consumer_result.get("data", "")
        print(f"\n✅ Consumer Token: {token}")

        # Step 2 — Trigger fire karo
        trigger_result = cb.fire_trigger(
            variable_name=variable,
            consumer_token=token,
            page="test",
            direction="Neutral"
        )
        print(f"✅ Trigger fired: {trigger_result}")

        return jsonify({
            "status": "success",
            "token": token,
            "trigger": trigger_result
        })
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000)