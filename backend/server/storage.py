"""
Server-side persistent storage.

Two JSON files:
  - data/sites.json : { site_id -> { cb_customer_id, cb_secret_encrypted, webflow_site_id, ... } }
  - data/rules.json : [ { rule_id, site_id, page_url, selector, cb_variable_name, ... } ]

CB secrets are encrypted at rest with Fernet (symmetric AES) using a key
loaded from the STORAGE_KEY env var. If STORAGE_KEY is unset, a key file
is auto-generated on first run (NOT recommended for production — set
STORAGE_KEY in your deployment env).
"""

import os
import json
import uuid
import threading
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet


# ─────────────────────────────────────────────
# Encryption setup
# ─────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_SITES_FILE = os.path.join(_DATA_DIR, "sites.json")
_RULES_FILE = os.path.join(_DATA_DIR, "rules.json")
_KEY_FILE = os.path.join(_DATA_DIR, ".storage_key")

os.makedirs(_DATA_DIR, exist_ok=True)


def _load_or_create_key() -> bytes:
    env_key = os.environ.get("STORAGE_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            return f.read().strip()
    # First run, no env var — generate and persist
    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    os.chmod(_KEY_FILE, 0o600)
    return key


_fernet = Fernet(_load_or_create_key())
_lock = threading.RLock()


def _encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


# ─────────────────────────────────────────────
# Low-level JSON file I/O
# ─────────────────────────────────────────────

def _read_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ─────────────────────────────────────────────
# Sites
# ─────────────────────────────────────────────

def list_sites() -> list[dict]:
    """Returns sites WITHOUT decrypted secrets (safe for API responses)."""
    with _lock:
        raw = _read_json(_SITES_FILE, {})
    out = []
    for site_id, rec in raw.items():
        out.append({
            "site_id": site_id,
            "name": rec.get("name", ""),
            "webflow_site_id": rec.get("webflow_site_id", ""),
            "origin": rec.get("origin", ""),
            "cb_customer_id": rec.get("cb_customer_id"),
            "has_secret": bool(rec.get("cb_secret_encrypted")),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
        })
    return out


def get_site(site_id: str, with_secret: bool = False) -> Optional[dict]:
    """
    Returns site record. If with_secret=True, includes the decrypted CB secret.
    Use with_secret=True ONLY in server-internal code paths — never return
    the result directly to a browser.
    """
    with _lock:
        raw = _read_json(_SITES_FILE, {})
    rec = raw.get(site_id)
    if not rec:
        return None
    out = {
        "site_id": site_id,
        "name": rec.get("name", ""),
        "webflow_site_id": rec.get("webflow_site_id", ""),
        "origin": rec.get("origin", ""),
        "cb_customer_id": rec.get("cb_customer_id"),
        "has_secret": bool(rec.get("cb_secret_encrypted")),
        "created_at": rec.get("created_at"),
        "updated_at": rec.get("updated_at"),
    }
    if with_secret and rec.get("cb_secret_encrypted"):
        try:
            out["cb_secret"] = _decrypt(rec["cb_secret_encrypted"])
        except Exception:
            out["cb_secret"] = None
    return out


def upsert_site(
    site_id: Optional[str] = None,
    name: str = "",
    webflow_site_id: str = "",
    origin: str = "",
    cb_customer_id: Optional[int] = None,
    cb_secret: Optional[str] = None,
) -> dict:
    """
    Create a new site or update an existing one. Returns the safe (no-secret)
    record. If cb_secret is provided, it is encrypted before persisting.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        raw = _read_json(_SITES_FILE, {})
        if site_id and site_id in raw:
            rec = raw[site_id]
        else:
            site_id = site_id or str(uuid.uuid4())
            rec = {"created_at": now}
            raw[site_id] = rec

        if name:
            rec["name"] = name
        if webflow_site_id:
            rec["webflow_site_id"] = webflow_site_id
        if origin:
            rec["origin"] = origin
        if cb_customer_id is not None:
            rec["cb_customer_id"] = int(cb_customer_id)
        if cb_secret:
            rec["cb_secret_encrypted"] = _encrypt(cb_secret)
        rec["updated_at"] = now

        _write_json(_SITES_FILE, raw)

    return get_site(site_id) or {}


def delete_site(site_id: str) -> bool:
    with _lock:
        raw = _read_json(_SITES_FILE, {})
        if site_id not in raw:
            return False
        del raw[site_id]
        _write_json(_SITES_FILE, raw)
        # Also delete all rules for this site
        rules = _read_json(_RULES_FILE, [])
        rules = [r for r in rules if r.get("site_id") != site_id]
        _write_json(_RULES_FILE, rules)
    return True


def find_site_by_origin(origin: str) -> Optional[dict]:
    """
    Look up a site by its origin (e.g. 'https://my-site.webflow.io').
    Used by the beacon endpoint to identify which site a click came from.
    Returns full record WITH decrypted secret (server-internal only).
    """
    if not origin:
        return None
    origin = origin.rstrip("/")
    with _lock:
        raw = _read_json(_SITES_FILE, {})
    for site_id, rec in raw.items():
        if (rec.get("origin") or "").rstrip("/") == origin:
            return get_site(site_id, with_secret=True)
    return None


# ─────────────────────────────────────────────
# Rules
# ─────────────────────────────────────────────

def list_rules(site_id: Optional[str] = None) -> list[dict]:
    with _lock:
        rules = _read_json(_RULES_FILE, [])
    if site_id:
        rules = [r for r in rules if r.get("site_id") == site_id]
    return rules


def add_rule(rule: dict) -> dict:
    rule.setdefault("rule_id", str(uuid.uuid4()))
    rule.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    with _lock:
        rules = _read_json(_RULES_FILE, [])
        rules.append(rule)
        _write_json(_RULES_FILE, rules)
    return rule


def delete_rule(rule_id: str) -> bool:
    with _lock:
        rules = _read_json(_RULES_FILE, [])
        before = len(rules)
        rules = [r for r in rules if r.get("rule_id") != rule_id]
        if len(rules) == before:
            return False
        _write_json(_RULES_FILE, rules)
    return True


def find_matching_rules(site_id: str, page_url: str, selector: str) -> list[dict]:
    """
    Used by the beacon endpoint: given a click, find rules that match.
    Matching is exact on (site_id, page_url, selector) OR (site_id, selector)
    if the rule has no page_url scope.
    """
    matches = []
    page_url_norm = (page_url or "").rstrip("/")
    selector_norm = (selector or "").strip()
    for r in list_rules(site_id):
        if r.get("selector", "").strip() != selector_norm:
            continue
        rule_page = (r.get("page_url") or "").rstrip("/")
        if rule_page and rule_page != page_url_norm:
            continue
        matches.append(r)
    return matches
