# CentreBlock Webflow Add-on — Complete Package

Is folder mein 2 parts hain — dono deploy karne padenge.

```
.
├── backend/                   ← Step 1: Iss server ko Render/Heroku pe deploy karo
│   ├── server/                  Flask app
│   ├── beacon/                  Dumb tracker (visitor browser mein chalega)
│   ├── designer_app/            Standalone version (Webflow marketplace ke bina test ke liye)
│   └── README.md
│
├── webflow_extension/         ← Step 2: Webflow CLI se bundle banao, Webflow pe upload karo
│   ├── webflow.json             Extension manifest
│   ├── package.json
│   ├── public/                  Designer mein iframe ke andar dikhega
│   └── PUBLISHING_GUIDE.md      ⭐ FULL STEP-BY-STEP GUIDE — yahan se shuru karo
│
└── README.md (this file)
```

## Yahan se shuru karo

**`webflow_extension/PUBLISHING_GUIDE.md` file kholo** — usmein zero se Marketplace tak ka step-by-step process hai, 5 phases mein divided:

1. Backend deploy karna (~30 min)
2. Webflow account + App register karna (~10 min)
3. Extension bundle banake upload karna (~15 min)
4. Apne workspace mein test karna
5. Marketplace pe submit karna (optional, ~1-2 hours work + 10-15 din review)

## Architecture (quick reference)

```
                Webflow Designer
                ┌────────────────────┐
                │ Extension iframe   │ ──► talks to ──┐
                │ (webflow_extension)│                │
                └────────────────────┘                ▼
                                              ┌──────────────┐
  Published Webflow site                      │ Your backend │
  ┌─────────────────────────┐                 │   (backend/) │ ──► CentreBlock
  │ beacon.js (dumb tracker)│ ──► talks to ──►│              │     (server-side)
  └─────────────────────────┘                 └──────────────┘
```

- **Extension UI** Webflow servers pe hosted hai (iframe ke andar)
- **Beacon** aapke backend pe hosted hai (har Webflow site se accessed)
- **Backend** Render/Heroku pe hosted hai (aapka apna)
- **CB secret** sirf backend ke paas hai, kabhi browser tak nahi pahuchta

## Security summary (kya safe hai, kya nahi)

✅ Safe:
- CB customer secret browser tak nahi pahuchta
- Disk pe Fernet-encrypted
- API responses mein kabhi return nahi hota
- `beacon.js` mein CentreBlock ka koi reference bhi nahi

⚠️ Aapko karna hoga:
- Production mein `STORAGE_KEY` aur `ADMIN_TOKEN` env vars set karo
- HTTPS use karo (Render automatic deta hai)
- `data/` folder Git mein commit mat karo (`.gitignore` already added)
- `WEBFLOW_CLIENT_SECRET` aur Render dashboard ko 2FA se protect karo
