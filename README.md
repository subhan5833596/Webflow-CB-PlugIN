# Webflow ↔ CentreBlock Add-on

A Webflow **Designer App** + **server-side** CentreBlock integration.

This replaces the previous client-side `tracker.js` setup with an architecture
where **the visitor's browser never sees the CentreBlock customer secret, the
CentreBlock API URL, the variable list, or any rules.**

## What changed vs the v2 tracker

| Concern                          | Before (v2)                                        | After (this version)                                       |
|----------------------------------|----------------------------------------------------|------------------------------------------------------------|
| Where CB secret lives            | Hardcoded in `centreblock.py`, in source           | Per-site, encrypted on disk, set via Designer App UI       |
| Where CB API is called from      | Server, but tracker.js knew which variables exist  | Server only                                                |
| What browser script does         | Fetches token, fetches all variables, matches      | Sends `{selector, page_url, visitor_id}` and nothing else  |
| Dashboard                        | Flask HTML templates served from same server       | Webflow Designer App (iframe inside Webflow Designer)      |
| Per-customer support             | Single-tenant                                      | Multi-tenant — each Webflow user adds their own CB creds   |

## Architecture

```
┌─────────────────────────────────┐
│ Webflow Designer (in browser)   │
│ ┌─────────────────────────────┐ │
│ │ CentreBlock Tracker App     │ │  HTTPS (Bearer ADMIN_TOKEN)
│ │ (iframe, this repo's        │ ├────────────────┐
│ │  designer_app/ folder)      │ │                │
│ └─────────────────────────────┘ │                ▼
└─────────────────────────────────┘    ┌──────────────────────┐
                                       │ Flask server         │
┌─────────────────────────────────┐    │ - /api/sites         │
│ Published Webflow site          │    │ - /api/rules         │
│ (visitor's browser)             │    │ - /api/beacon        │
│  ┌────────────────┐             │    │ - /beacon.js         │
│  │ beacon.js (dumb)│            │    │                      │
│  └────┬───────────┘             │    │ stores: sites.json   │
│       │ POST /api/beacon        ├───►│        rules.json    │
│       │ { selector, page_url,   │    │ secrets: Fernet-     │
│       │   visitor_id }          │    │          encrypted   │
└───────┼─────────────────────────┘    └──────────┬───────────┘
                                                  │
                                                  ▼
                                       ┌──────────────────────┐
                                       │ CentreBlock API      │
                                       │ prod.centreblock.net │
                                       └──────────────────────┘
```

## Repository layout

```
.
├── server/                  ← Flask backend
│   ├── app.py               ← API routes (sites, rules, beacon, OAuth)
│   ├── centreblock.py       ← CB API client (no hardcoded credentials)
│   ├── storage.py           ← JSON file storage with Fernet encryption
│   ├── requirements.txt
│   └── data/                ← sites.json, rules.json (auto-created)
│
├── designer_app/            ← Webflow Designer App (single-page HTML)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── webflow.json         ← Webflow App manifest
│
├── beacon/
│   └── beacon.js            ← The "dumb" tracker script
│
├── Procfile                 ← Heroku/Render deploy
├── .env.example
└── README.md
```

## Local development

```bash
cd server
pip install -r requirements.txt
python app.py            # → http://localhost:5000
```

Then open `http://localhost:5000/app` in a browser — this is the Designer
App running standalone (without Webflow). Add a site, save your CentreBlock
credentials (`cb_customer_id=117`, `cb_secret=<your secret>`), discover
pages, and create rules.

To test the beacon, paste this on any HTML page on `localhost:5000` or
on a Webflow site that's been added in Setup:

```html
<script src="http://localhost:5000/beacon.js" defer></script>
```

Click around — every click POSTs to `/api/beacon`. Server logs will show
matching rules and CB triggers being fired.

## Production deployment

1. Generate a stable `STORAGE_KEY`:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Generate a random `ADMIN_TOKEN` (any long random string).

3. Deploy `server/` to Heroku / Render / Railway / Fly.io. Set these env vars:

   ```
   STORAGE_KEY=<from step 1>
   ADMIN_TOKEN=<from step 2>
   APP_BASE_URL=https://your-deployed-url.com
   ```

4. Open `https://your-deployed-url.com/app?admin=<ADMIN_TOKEN>` to use the
   Designer App standalone in your browser.

5. Add the beacon to your Webflow site (Project Settings → Custom Code →
   Footer Code):

   ```html
   <script src="https://your-deployed-url.com/beacon.js" defer></script>
   ```

## Publishing as a real Webflow App (optional)

To install this in the Webflow Designer (not just standalone), you'll need:

1. A Webflow developer account.
2. Register an app at https://webflow.com/dashboard/account/integrations.
3. Get the resulting `WEBFLOW_CLIENT_ID` and `WEBFLOW_CLIENT_SECRET`.
4. Set them as env vars on the server.
5. Set the Designer Extension public URI to `https://your-deployed-url.com/app`.
6. Upload `designer_app/webflow.json` (edit `homepage` and `publicUri` first).
7. Submit for review or use it as an unlisted dev app.

The Flask server already has `/oauth/authorize` and `/oauth/callback`
endpoints ready for this flow.

## Security notes

- **CB secret never touches the browser.** It is sent ONCE in a POST to
  `/api/sites`, encrypted at rest with Fernet (`STORAGE_KEY`), and never
  included in any response.
- **The beacon sends only `selector`, `page_url`, `visitor_id`** — no tokens,
  no variable names, no rule details. The server identifies the site by
  the `Origin` header.
- **`/api/sites` and `/api/rules` are gated** by `Authorization: Bearer
  <ADMIN_TOKEN>` when `ADMIN_TOKEN` is set.
- **The beacon endpoint is intentionally open** (any origin) because it
  must accept clicks from the public Webflow site. It cannot leak anything
  useful — even an unknown origin gets a silent 200.
- **The token cache** (`_token_cache` in `app.py`) is per-process and
  in-memory. For multi-worker deployments, swap it for Redis if you want
  cache-sharing; otherwise each worker just makes a fresh CB consumer call
  on first click (which is harmless — CB returns the same token for the
  same UUID).

## Migrating from v2

1. Stop your old Flask server.
2. Note your CB customer ID (was hardcoded as `117`) and CB secret.
3. Deploy this new server.
4. Open `/app`, add your site with the same origin, paste your CB customer ID
   and secret into the form. Existing CB variables remain — no data loss.
5. Replace your Webflow Footer Code's `tracker.js` URL with `/beacon.js`
   from the new server.
6. Re-create your tracking rules in the Designer App (Setup → Rules tab).
   The CB variables will not be duplicated — the server checks for existing
   variables first.

## Files retired from v2

- `static/tracker.js`         → replaced by `beacon/beacon.js`
- `static/dashboard.js`       → replaced by `designer_app/app.js`
- `templates/*.html`          → replaced by `designer_app/index.html`
- Hardcoded credentials       → encrypted per-site storage
