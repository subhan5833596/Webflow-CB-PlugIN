import uuid
import requests
import datetime

SUPABASE_URL = "https://dcappavpcbxdcxdurrsp.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRjYXBwYXZwY2J4ZGN4ZHVycnNwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM3MzY4ODksImV4cCI6MjA4OTMxMjg4OX0.LWNTG4pca4gzi4hdgtofOf9TzDGo9JyOZLuANlMy3ks"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Example insert for events table
event_data = {
    "id": str(uuid.uuid4()),  # unique id
    "data": {
        "user": "anonymous",
        "website_url": "https://example.com",
        "page_url": "https://example.com/home",
        "selector": "#hero > button:nth-of-type(1)",
        "action": "click",
        "matched_rule": True,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
}

res = requests.post(f"{SUPABASE_URL}/rest/v1/events", json=event_data, headers=HEADERS)

print("Status code:", res.status_code)
print("Response text:", res.text)

# Only parse JSON if non-empty
try:
    print("JSON:", res.json())
except Exception as e:
    print("Cannot parse JSON:", e)



# # INSERT
# data = {
#     "webflow_url": "https://example.com",
#     "pages": {"home": "/", "about": "/about"}
# }
# res = requests.post(f"{SUPABASE_URL}/rest/v1/site_config", json=data, headers=HEADERS)
# print("site_config insert:", res.json())

# # SELECT
# res = requests.get(f"{SUPABASE_URL}/rest/v1/site_config?webflow_url=eq.https://example.com", headers=HEADERS)
# print("site_config select:", res.json())


# # INSERT
# data = {
#     "web_url": "https://example.com",
#     "page_url": "/about",
#     "elements": {"button": "Sign Up", "text": "Welcome"}
# }
# res = requests.post(f"{SUPABASE_URL}/rest/v1/elements", json=data, headers=HEADERS)
# print("elements insert:", res.json())

# # SELECT
# res = requests.get(f"{SUPABASE_URL}/rest/v1/elements?web_url=eq.https://example.com", headers=HEADERS)
# print("elements select:", res.json())



# # INSERT
# data = {
#     "data": {"rule_name": "no_duplicate", "enabled": True}
# }
# res = requests.post(f"{SUPABASE_URL}/rest/v1/rules", json=data, headers=HEADERS)
# print("rules insert:", res.json())

# # SELECT
# res = requests.get(f"{SUPABASE_URL}/rest/v1/rules", headers=HEADERS)
# print("rules select:", res.json())

# # INSERT
# data = {
#     "data": {"event_name": "page_visited", "page": "/about"}
# }
# res = requests.post(f"{SUPABASE_URL}/rest/v1/events", json=data, headers=HEADERS)
# print("events insert:", res.json())

# # SELECT
# res = requests.get(f"{SUPABASE_URL}/rest/v1/events", headers=HEADERS)
# print("events select:", res.json())