# CentreBlock Webflow Tracker

A **database-free** Python/Flask visitor tracking tool for Webflow sites, powered by three CentreBlock APIs.

---

## Architecture

```
Webflow visitor
     │
     ▼
tracker.js  (embedded in Webflow footer)
     │
     ├─► POST /get_consumer_token   ─► CentreBlock  /api/v1/consumer
     │         returns { token }
     │
     └─► POST /track_event          ─► CentreBlock  /api/v1/trigger/<variable_name>
              (on every matched click)

Dashboard (you)
     │
     ├─► /tracking_rule  ─► POST /add_rule  ─► CentreBlock  /api/v1/variables
     │
     └─► /tracking_history  ─► GET /get_events  (in-process log)
```

No Supabase, no PostgreSQL, no SQLite — all behavioural state is stored in CentreBlock.

---

## The 3 CentreBlock APIs

| API        | Endpoint                               | Used when                            |
|------------|----------------------------------------|--------------------------------------|
| Consumer   | `POST /api/v1/consumer`                | Visitor lands on any page            |
| Variable   | `POST /api/v1/variables`               | Tracking rule is created in dashboard|
| Trigger    | `POST /api/v1/trigger/<variable_name>` | Visitor clicks a tracked element     |

### Hardcoded credentials (`centreblock.py`)
```python
CB_BASE_URL      = "https://prod.centreblock.net/api/v1"
CUSTOMER_ID      = 117
CUSTOMER_SECRET  = "If/pKChUuAjLGYBv+1Ftgdp8vdmO/fHi9eEmnJiDRkWDDYLV1nv2z4N2QEleLaXUTNXrHrY7VaIkF+viG43btg=="
```

---

## Running locally

```bash
pip install -r requirements.txt
python app.py
# → http://127.0.0.1:5000
```

## Deploying to Heroku / Render / Railway

```bash
git init && git add . && git commit -m "init"
heroku create my-cb-tracker
git push heroku main
```

---

## Embedding in Webflow

1. In Webflow → **Project Settings → Custom Code → Footer Code**, add:

```html
<script src="https://YOUR-BACKEND-URL/static/tracker.js"></script>
```

2. The script will:
   - Obtain a CentreBlock consumer token for the visitor (cached in `sessionStorage`)
   - Fetch your active tracking rules
   - Attach event listeners to matched elements
   - Fire a CentreBlock trigger on every match

---

## Dashboard workflow

1. **Setup** (`/setup_page`) — Enter your Webflow URL; all internal pages are discovered automatically.
2. **Rules** (`/tracking_rule`) — Pick a page, pick an element, set a CB variable name + weights, click **Add Rule**. The variable is created in CentreBlock immediately.
3. **History** (`/tracking_history`) — See all triggers fired in the current session with CB API response status.

---

## Files

```
app.py            ← Flask routes (no DB)
centreblock.py    ← CentreBlock API client (consumer / variable / trigger)
static/
  tracker.js      ← Embedded in Webflow footer
  dashboard.js    ← Dashboard UI logic
  styles.css      ← Styles
templates/
  index.html
  setup.html
  tracking_rule.html
  tracking_history.html
requirements.txt
Procfile
```
