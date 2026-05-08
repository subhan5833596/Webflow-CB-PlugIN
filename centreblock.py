"""
CentreBlock API client
Wraps the 3 core CentreBlock APIs:
  1. Consumer  – GET or create a consumer token by UUID (IP)
  2. Variable  – Create / list variables
  3. Trigger   – Fire a trigger for a consumer
"""

import requests
from datetime import datetime


CB_BASE_URL = "https://prod.centreblock.net/api/v1"
CUSTOMER_ID = 117
CUSTOMER_SECRET = "If/pKChUuAjLGYBv+1Ftgdp8vdmO/fHi9eEmnJiDRkWDDYLV1nv2z4N2QEleLaXUTNXrHrY7VaIkF+viG43btg=="


def _customer_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-centreblock-token": CUSTOMER_SECRET,
    }


def _consumer_headers(token: str) -> dict:
    return {
        "Content-Type": "application/json",
        "x-centreblock-consumer-token": token,
    }


# ─────────────────────────────────────────────
# 1. CONSUMER API
# ─────────────────────────────────────────────

def get_or_create_consumer(
    uuid: str,
    audiences: list[str] | None = None,
    tags: dict | None = None,
    token_ttl: int = 10,
) -> dict:
    """
    POST /consumer
    Returns the token for the given UUID.
    If the consumer already exists CentreBlock just returns the same token.

    Args:
        uuid: Unique identifier for the visitor (e.g. IP address or session ID)
        audiences: List of audience IDs; defaults to ["default"]
        tags: Optional key/value tags to attach to the consumer
        token_ttl: Token lifetime in days (default 10)

    Returns:
        {"status": "success", "data": "<token>"}
    """
    if audiences is None:
        audiences = ["default"]

    now = datetime.utcnow().isoformat()
    payload = {
        "uuid": uuid,
        "customerId": CUSTOMER_ID,
        "createdAt": now,
        "audiences": audiences,
        "tokenTimeToLive": token_ttl,
        "tags": {
            "token_request_ts": now,
            **(tags or {}),
        },
    }

    print(f"CB Consumer Payload: {payload}")
    resp = requests.post(
        f"{CB_BASE_URL}/consumer",
        json=payload,
        headers=_customer_headers(),
        timeout=10,
    )
    print(f"CB Consumer Response [{resp.status_code}]: {resp.text}")
    resp.raise_for_status()
    return resp.json()   # {"status": "success", "data": "<token>"}


# ─────────────────────────────────────────────
# 2. VARIABLE API
# ─────────────────────────────────────────────

def variable_exists(name: str) -> bool:
    """
    GET /csv/<customer_id>
    Check karo agar variable pehle se exist karta hai ya nahi.
    CSV download karke variable names mein dhundta hai.
    """
    try:
        csv_text = get_variables_csv()
        lines = [l.strip() for l in csv_text.strip().splitlines() if l.strip()]
        # First line is header — skip karo
        for line in lines[1:]:
            var_name = line.split(",")[0].strip().lower()
            if var_name == name.lower():
                print(f"Variable '{name}' pehle se exist karta hai CB mein — skip")
                return True
        return False
    except Exception as e:
        print(f"Variable exist check fail: {e}")
        return False  # Safe side pe naya bana do


def create_variable(
    name: str,
    weight_for_customer: float = 15.0,
    weight_for_default: float = 15.0,
    direction: str = "Positive",
    tags: dict | None = None,
    leaving_link: str = "",
    label: str = "",
) -> dict:
    """
    POST /variables
    Variable exist karta hai toh skip, nahi karta toh create karo.

    Args:
        name:                  Variable name (lowercase + underscores only)
        weight_for_customer:   Weight for 'customer' audience
        weight_for_default:    Weight for 'default' audience
        direction:             "Positive", "Negative", or "Neutral"
        tags:                  Extra tags
        leaving_link:          Outbound URL (agar element bahar jaata hai)
        label:                 Human readable label

    Returns:
        {"skipped": True}  agar already exist karta hai
        CB response dict   agar naya bana
    """
    clean_name = name.lower().replace(" ", "_")
    # Sirf a-z aur _ allowed — numbers bhi remove
    import re
    clean_name = re.sub(r"[^a-z_]", "_", clean_name)
    clean_name = re.sub(r"_+", "_", clean_name).strip("_")
    # Number se start nahi ho sakta — cb_ prefix lagao
    if clean_name and clean_name[0] == "_" or not clean_name[0].isalpha():
        clean_name = "cb_" + clean_name

    # Pehle check karo — exist karta hai?
    if variable_exists(clean_name):
        return {"skipped": True, "name": clean_name, "message": "Variable already exists"}

    # Tags build karo — whitepaper ke according
    variable_tags = tags or {}
    if leaving_link:
        variable_tags["leaving_link"] = leaving_link   # outbound URL — whitepaper section 6.2
    if label:
        variable_tags["label"] = label                 # human readable label

    payload = {
        "name": clean_name,
        "categories": {
            "customer": weight_for_customer,
            "default": weight_for_default,
        },
        "tags": variable_tags,
    }

    print(f"CB Variable Payload: {payload}")
    resp = requests.post(
        f"{CB_BASE_URL}/variables/",
        json=payload,
        headers=_customer_headers(),
        timeout=10,
    )
    print(f"CB Variable Response [{resp.status_code}]: {resp.text}")
    resp.raise_for_status()
    print(f"Variable '{clean_name}' CB mein ban gaya ✅")
    return resp.json()


def get_variables_csv() -> str:
    """
    GET /csv/<customer_id>
    Returns the raw CSV string of all variables for this customer.
    """
    resp = requests.get(
        f"{CB_BASE_URL}/csv/{CUSTOMER_ID}",
        headers={"x-centreblock-token": CUSTOMER_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.text


# ─────────────────────────────────────────────
# 3. TRIGGER API
# ─────────────────────────────────────────────

def fire_trigger(
    variable_name: str,
    consumer_token: str,
    page: str = "",
    direction: str = "Neutral",
    extra_tags: dict | None = None,
) -> dict:
    """
    POST /trigger/<variable_name>
    Inform CentreBlock that a consumer interacted with a variable.

    Args:
        variable_name:   The CB variable name (e.g. "menu_home")
        consumer_token:  Token obtained from get_or_create_consumer()
        page:            Current page label / URL (stored as tag)
        direction:       "Positive", "Negative", or "Neutral"
        extra_tags:      Any additional tags to attach to the trigger event

    Returns:
        {"status": <http_status_code>}
    """
    tags = {
        "page": page,
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