"""
CentreBlock API client.

Credentials are NOT hardcoded. They are passed in per call and come from
the per-site record in data/sites.json. The browser never sees these.
"""

import re
import requests
from datetime import datetime
from typing import Optional

CB_BASE_URL = "https://prod.centreblock.net/api/v1"


# ─────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────

def _customer_headers(secret: str) -> dict:
    return {
        "Content-Type": "application/json",
        "x-centreblock-token": secret,
    }


def _consumer_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "x-centreblock-consumer-token": token,
    }


def _sanitize_tag(val) -> str:
    # CB tag keys/values: alphanumeric only
    return re.sub(r"[^a-zA-Z0-9]", "", str(val))


# ─────────────────────────────────────────────
# 1. CONSUMER API
# ─────────────────────────────────────────────

def get_or_create_consumer(
    customer_id: int,
    secret: str,
    uuid: str,
    audiences: Optional[list[str]] = None,
    tags: Optional[dict] = None,
    token_ttl: int = 10,
) -> dict:
    """
    POST /consumer
    Returns the consumer token for the given UUID.

    Args:
        customer_id: CB customer ID (per-site, from sites.json)
        secret:      CB customer secret (per-site, never exposed to browser)
        uuid:        Unique visitor identifier (IP, session id, etc.)
        audiences:   Audience list (default: ["default"])
        tags:        Optional alphanumeric-only tags
        token_ttl:   Token lifetime in days

    Returns:
        {"status": "success", "data": "<token>"}
    """
    if audiences is None:
        audiences = ["default"]

    clean_tags = {
        _sanitize_tag(k): _sanitize_tag(v)
        for k, v in (tags or {}).items()
        if _sanitize_tag(k) and _sanitize_tag(v)
    }

    payload = {
        "uuid": uuid,
        "customerId": customer_id,
        "createdAt": datetime.utcnow().isoformat(),
        "audiences": audiences,
        "tokenTimeToLive": token_ttl,
        "tags": clean_tags,
    }

    resp = requests.post(
        f"{CB_BASE_URL}/consumer",
        json=payload,
        headers=_customer_headers(secret),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────
# 2. VARIABLE API
# ─────────────────────────────────────────────

def get_variables_csv(customer_id: int, secret: str) -> str:
    """GET /csv/<customer_id> — raw CSV of all variables for this customer."""
    resp = requests.get(
        f"{CB_BASE_URL}/csv/{customer_id}",
        headers={"x-centreblock-token": secret},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.text


def variable_exists(customer_id: int, secret: str, name: str) -> bool:
    """Check if a variable with this name already exists in CB."""
    try:
        csv_text = get_variables_csv(customer_id, secret)
        lines = [l.strip() for l in csv_text.strip().splitlines() if l.strip()]
        for line in lines[1:]:  # skip header
            first_col = line.split(",")[0].strip().strip('"').lower()
            if first_col == name.lower():
                return True
        return False
    except Exception:
        # On error, return False so caller will try to create — CB will
        # reject duplicates on its side anyway.
        return False


def _clean_variable_name(name: str) -> str:
    """CB variable names: lowercase, alpha + underscore, must start with letter."""
    n = name.lower().replace(" ", "_")
    n = re.sub(r"[^a-z_]", "_", n)
    n = re.sub(r"_+", "_", n).strip("_")
    if not n:
        return "cb_var"
    if not n[0].isalpha():
        n = "cb_" + n
    return n


def create_variable(
    customer_id: int,
    secret: str,
    name: str,
    weight_for_customer: float = 15.0,
    weight_for_default: float = 15.0,
    direction: str = "Positive",
    leaving_link: str = "",
    label: str = "",
) -> dict:
    """
    POST /variables
    If variable already exists in CB, returns {"skipped": True}.
    """
    clean_name = _clean_variable_name(name)

    if variable_exists(customer_id, secret, clean_name):
        return {"skipped": True, "name": clean_name, "message": "Variable already exists"}

    variable_tags = {}
    if label:
        variable_tags["label"] = _sanitize_tag(label)

    payload = {
        "name": clean_name,
        "categories": {
            "customer": weight_for_customer,
            "default": weight_for_default,
        },
        "tags": variable_tags,
    }
    if leaving_link:
        payload["leavingLink"] = leaving_link

    resp = requests.post(
        f"{CB_BASE_URL}/variables/",
        json=payload,
        headers=_customer_headers(secret),
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()
    result["name"] = clean_name
    return result


# ─────────────────────────────────────────────
# 3. TRIGGER API
# ─────────────────────────────────────────────

def fire_trigger(
    variable_name: str,
    consumer_token: str,
    page: str = "",
    direction: str = "Neutral",
    extra_tags: Optional[dict] = None,
) -> dict:
    """
    POST /trigger/<variable_name>
    Inform CB that a consumer interacted with a variable.

    Note: this call uses the *consumer* token, not the customer secret.
    """
    tags = {
        "page": _sanitize_tag(page)[:60],
        "direction": direction,
        **(extra_tags or {}),
    }

    resp = requests.post(
        f"{CB_BASE_URL}/trigger/{variable_name}",
        json={"tags": tags},
        headers=_consumer_headers(consumer_token),
        timeout=10,
    )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Trigger '{variable_name}' failed [{resp.status_code}]: {resp.text}"
        )

    return {"status": resp.status_code}
