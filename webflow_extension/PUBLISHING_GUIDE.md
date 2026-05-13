# Webflow pe Publish kaise karein — Step-by-Step Guide

Yeh guide aapko zero se Webflow Marketplace tak le jayegi.

---

## Quick overview — ye 3 cheezein chahiye

1. **Aapka backend server** kahin deploy hua ho (Heroku/Render/Railway/Fly.io) — `webflow_cb_addon/server/` folder
2. **Webflow Designer Extension** Webflow ko upload karna — `webflow_cb_extension/` folder (CLI format mein)
3. **Webflow Marketplace submission** form bharna — Webflow team review karegi

---

## PHASE 1 — Backend deploy karo (~30 min)

Pehle backend live hona chahiye taaki extension usse baat kar sake.

### Option A: Render.com (sabse easy, free tier mein chalega)

1. https://render.com pe account banao
2. **New → Web Service** → GitHub repo connect karo (`webflow_cb_addon` folder push karo GitHub pe)
3. Configuration:
   - **Build command**: `pip install -r server/requirements.txt`
   - **Start command**: `gunicorn --chdir server app:app --bind 0.0.0.0:$PORT`
   - **Environment**: Python 3.11+
4. **Environment variables** (Settings tab):
   ```
   STORAGE_KEY=<generate karke daalo>
   ADMIN_TOKEN=<random long string>
   APP_BASE_URL=https://your-render-url.onrender.com
   ```

   `STORAGE_KEY` generate karne ke liye apne local pe ye chalao:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

5. Deploy karo. URL note karo — example: `https://centreblock-tracker.onrender.com`

### Verify
Browser mein kholo: `https://your-server.onrender.com/` — JSON response milna chahiye `{"service": "webflow-centreblock-addon", "status": "ok"}`.

---

## PHASE 2 — Webflow App register karo (~10 min)

1. https://webflow.com → Sign in (agar account nahi hai to banao)
2. **Account → Security** → Two-Factor Authentication **on karo**. Iske bina bundle upload nahi hoga.
3. Workspace banao (free Starter chalega) ya existing workspace use karo
4. **Workspace Settings → Apps & Integrations** tab
5. Scroll karke **"Develop"** section mein **"Create an App"** click karo
6. Form bharo:

   | Field | Value |
   |---|---|
   | App name | CentreBlock Tracker |
   | App description | Track Webflow visitor clicks to CentreBlock variables |
   | Homepage URL | `https://your-server.onrender.com` |
   | Building blocks | ✅ **Designer Extension** check karo |
   | Scopes | `sites:read`, `pages:read` |
   | Redirect URI | `https://your-server.onrender.com/oauth/callback` |

7. Submit karo. Aapko **Client ID** aur **Client Secret** dikhega — dono **abhi note karo** (Secret dobara nahi dikhega)

8. Wapis Render dashboard pe jaake ye 3 env vars **add karo**:
   ```
   WEBFLOW_CLIENT_ID=<jo abhi mila>
   WEBFLOW_CLIENT_SECRET=<jo abhi mila>
   WEBFLOW_REDIRECT_URI=https://your-server.onrender.com/oauth/callback
   ```

---

## PHASE 3 — Extension bundle banao aur upload karo (~15 min)

### Step 1: Local pe Webflow CLI install karo

```bash
# Node.js >= 18 chahiye
node --version    # Agar 18+ nahi hai, https://nodejs.org se install karo

# Webflow CLI
npm install -g @webflow/webflow-cli

# Verify
webflow --version
```

### Step 2: Extension folder ready karo

Maine `webflow_cb_extension/` folder bana diya hai aapke liye. Iska structure:
```
webflow_cb_extension/
├── webflow.json           ← extension manifest
├── package.json
└── public/                ← jo Webflow Designer mein dikhega
    ├── index.html
    ├── app.js
    └── styles.css
```

### Step 3: Bundle banao

```bash
cd webflow_cb_extension
webflow extension bundle
```

Ye `bundle.zip` file banayega project ki root mein. Ye 5 MB se kam hona chahiye (humara ~27 KB hai, no problem).

### Step 4: Webflow pe upload karo

1. Webflow → **Workspace Settings → Apps & Integrations → Develop** section
2. Apni "CentreBlock Tracker" app dhundo, **"…"** menu pe click karo
3. **"Publish extension version"** select karo
4. `bundle.zip` upload karo
5. Version notes likho (jaise "v1.0 - initial release")
6. Upload complete hone par success message dikhega

---

## PHASE 4 — Apne workspace mein test karo

1. Apni workspace mein koi bhi Webflow site kholo (test site banao agar nahi hai)
2. Webflow Designer mein, **"E"** key press karo — Apps panel khulega
3. **"CentreBlock Tracker"** app dhundo
4. **"Launch App"** click karo (NOT "Launch development app" — wo local dev ke liye hai)
5. Extension iframe panel khulega Designer mein
6. **Setup tab**:
   - Backend URL: `https://your-server.onrender.com`
   - Admin token: jo Phase 1 mein generate kiya tha
   - **"Save backend config"** click karo
7. Sites list khali dikhegi — **"Add a new site"** form bharo:
   - Name: My Test Site
   - Origin: aapki Webflow site ka published URL (e.g. `https://my-site.webflow.io`)
   - CB customer ID: aapka CentreBlock customer ID (purana `117`)
   - CB secret: aapka CB secret
   - Save
8. Agar credentials sahi hain to "Saved ✓" dikhega. Server ne CentreBlock se verify kar liya.

### Beacon install karo aapki Webflow site mein

1. Aapki Webflow project ki **Site Settings → Custom Code → Footer Code**
2. Paste karo:
   ```html
   <script src="https://your-server.onrender.com/beacon.js" defer></script>
   ```
3. **Publish** site karo
4. Site visit karo, kuch clicks karo
5. Wapis Designer Extension mein **Rules tab** → rules banao
6. Server logs dekho — CentreBlock triggers fire ho rahe honge

---

## PHASE 5 — Marketplace pe submit karo (~1-2 hours work + 10-15 days review)

Ye **optional** hai. Aapka app abhi bhi pura kaam karta hai — bas wo "private" hai (sirf aap aur jinhe aap invite karo). Public Marketplace pe daalne se duniya bhar ke Webflow users isse install kar payenge.

### Submission requirements:

1. **App icon** — 120x120 px PNG. CentreBlock ka logo ya custom design
2. **Screenshots** — 3-5 screenshots app ke working ke
3. **Demo video** — 2-5 minute video showing full walkthrough (Loom/YouTube link)
4. **Support email** — jahan users contact kar sakein
5. **Privacy policy URL** — kyunki aap user secrets store kar rahe ho, ye **mandatory** hai
6. **Terms of Service URL**
7. **Marketing copy** — short description (160 chars), long description, feature list

### Submission process:

1. Webflow → Workspace Settings → Apps & Integrations → aapki app → **"Submit for Marketplace"**
2. Saari fields fill karo
3. Submit
4. Webflow team **10-15 business days** mein review karegi
5. Email se approve ya reject ka notification milega
6. Reject hua to feedback ke saath aata hai, fix karke re-submit kar sakte ho

### Marketplace submission ki important guidelines (Webflow ne mention kiya):

- App backend live aur fully functional hona chahiye review ke time pe
- Reviewers ko **test credentials** chahiye honge (CB ke test customer ID/secret jo unhe de sako)
- Code "well-organized" aur readable hona chahiye
- `eval()` ya direct DOM manipulation jaisi unsafe patterns nahi
- External iframes sirf authentication ke liye allowed (humara app sirf authentication ke liye iframe use nahi karta, so safe)

---

## Important honest notes

### 1. Free tier limitations
Render free tier 15 min idle ke baad sleep ho jata hai. Pehla request slow hoga (~30 sec). Production ke liye paid tier ($7/month) ya Heroku/Railway use karo.

### 2. Data persistence
Mera current setup `data/*.json` files mein store karta hai. Render free tier pe ye **redeploy hone par lost ho jata hai**. Production ke liye:
- PostgreSQL add karo (Render free Postgres add-on dega), ya
- Render Disks ($1/month, persistent storage)

Agar aap chaho to main `storage.py` ko Postgres ke liye refactor kar du.

### 3. Marketplace fee
Webflow Marketplace pe paid apps publish karne par Webflow commission leta hai. Free apps pe no fee.

### 4. Without marketplace publishing
Agar aap public publish nahi karna chahte (sirf apne use ya specific clients ke liye), to **Phase 5 skip kar do**. App private rahega aapki workspace mein, aap collaborators ko share kar sakte ho.

---

## Troubleshooting

**"Bundle upload disabled"** — 2FA on nahi hai. Account Settings → Security mein on karo.

**"Launch App button greyed out"** — App workspace mein installed nahi hai. Workspace Settings → Apps → Install karo.

**Extension iframe blank/loading forever** — Browser console kholo (F12). Common reasons:
- `webflow.json` mein typo
- `public/` folder ka koi file missing
- `index.html` mein absolute paths use kiye (always `./styles.css` use karo, not `/styles.css`)

**"Backend URL not configured"** error inside extension** — Setup tab mein backend URL save karna bhul gaye

**CB credentials rejected (403)** — CentreBlock se customer ID/secret verify karo

---

## Summary checklist

Phase 1 — Backend deploy:
- [ ] Render/Heroku/Railway pe `webflow_cb_addon/server/` deploy
- [ ] `STORAGE_KEY`, `ADMIN_TOKEN`, `APP_BASE_URL` env vars set
- [ ] `https://your-server.onrender.com/` accessible

Phase 2 — Webflow App register:
- [ ] Webflow account banaya
- [ ] 2FA enabled
- [ ] App created in workspace
- [ ] Client ID + Secret saved aur backend env vars mein add kiya

Phase 3 — Extension upload:
- [ ] Webflow CLI installed
- [ ] `webflow extension bundle` chala
- [ ] `bundle.zip` Workspace Settings se upload kiya

Phase 4 — Test:
- [ ] App workspace mein install kiya
- [ ] Designer mein "Launch App" se khula
- [ ] Backend URL save kiya, site add kiya, rule banaya
- [ ] Webflow site mein beacon snippet paste kiya
- [ ] Click fire hone par CB trigger ja raha hai

Phase 5 (optional) — Marketplace:
- [ ] Privacy policy + ToS URLs bana liye
- [ ] Demo video ready
- [ ] Marketplace submission form bhara
