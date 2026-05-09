/**
 * CentreBlock Webflow Tracker
 * ─────────────────────────────────────────────
 * Paste this in Webflow → Project Settings → Custom Code → Footer:
 *   <script src="https://<your-backend>/static/tracker.js"></script>
 *
 * Flow:
 *  1. Visitor aaya → /get_consumer_token → token lo
 *  2. /cb_variables → saare variables lo, site se filter karo
 *  3. Page ke clickable elements pe listeners lagao
 *  4. Click hua → variable se match karo → /fire_trigger call karo
 */

const BACKEND_URL =
  "https://centreblock-webflow-tracker-h6c7c6c2bdawgeh4.canadacentral-01.azurewebsites.net"; // same origin, ya "https://your-backend.com"

// ────────────────────────────────────────────
// 1. Consumer Token
// ────────────────────────────────────────────

async function fetchConsumerToken() {
  const cached = sessionStorage.getItem("_cb_token");
  if (cached) return cached;

  // UUID = website domain (e.g. "www.dartmarketing.io" or "127.0.0.1_5000")
  const websiteDomain = window.location.host.replace(":", "_");

  const res = await fetch(`${BACKEND_URL}/get_consumer_token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      uuid: websiteDomain,
      entry_page: window.location.href,
      referer: document.referrer || "",
      audiences: ["default"],
    }),
  });

  const data = await res.json();
  if (data.token) {
    sessionStorage.setItem("_cb_token", data.token);
    console.log("[CB] Consumer token mila");
    return data.token;
  }
  console.warn("[CB] Token nahi mila:", data);
  return null;
}

// ────────────────────────────────────────────
// 2. CB Variables — backend se fetch + site filter
// ────────────────────────────────────────────

async function fetchVariables() {
  const cached = sessionStorage.getItem("_cb_variables");
  if (cached) return JSON.parse(cached);

  const res = await fetch(`${BACKEND_URL}/cb_variables`);
  const vars = await res.json();

  // Site name — domain se nikalo
  const domain = window.location.hostname.replace(/^www\./, "");
  const rawSite = domain
    .split(".")[0]
    .toLowerCase()
    .replace(/[^a-z]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  const prefix = /^[a-z]/.test(rawSite) ? rawSite : "site";

  // Sirf is site ke variables
  const filtered = vars.filter(
    (v) => v.name && v.name.startsWith(prefix + "_"),
  );
  console.log(
    `[CB] Variables: ${vars.length} total, ${filtered.length} for "${prefix}"`,
  );

  sessionStorage.setItem("_cb_variables", JSON.stringify(filtered));
  return filtered;
}

// ────────────────────────────────────────────
// 3. Match element → variable
// ────────────────────────────────────────────

function matchVariable(element, variables) {
  // Site name
  const domain = window.location.hostname.replace(/^www\./, "");
  const rawSite = domain
    .split(".")[0]
    .toLowerCase()
    .replace(/[^a-z]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  const siteName = /^[a-z]/.test(rawSite) ? rawSite : "site";

  // Page slug
  const pathOnly = window.location.pathname.replace(/^\/|\/$/g, "");
  const slug =
    (pathOnly.split("/").pop() || "home")
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "") || "home";

  // Element hints — text > id > first class
  const text = (element.textContent || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 25);
  const id = (element.id || "")
    .toLowerCase()
    .replace(/[^a-z]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 25);
  const cls =
    [...(element.classList || [])][0]
      ?.toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "") || "";

  const hints = [text, id, cls].filter(Boolean);

  for (const variable of variables) {
    const vname = variable.name || "";

    if (!vname.startsWith(siteName + "_")) continue;
    if (!vname.includes(slug)) continue;

    for (const hint of hints) {
      if (hint && vname.endsWith("_" + hint)) {
        console.log(`[CB] Match: "${element.textContent.trim()}" -> ${vname}`);
        return variable;
      }
    }
  }
  return null;
}

// ────────────────────────────────────────────
// 4. Trigger — backend ke through (CB URL expose nahi hogi)
// ────────────────────────────────────────────

async function fireTrigger(variableName, consumerToken) {
  console.log(`[CB] Trigger fire ho raha hai: ${variableName}`);

  const res = await fetch(`${BACKEND_URL}/fire_trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      variable_name: variableName,
      consumer_token: consumerToken,
      page: window.location.href,
      direction: "Neutral",
    }),
  });

  const data = await res.json().catch(() => res.text());
  if (res.ok) {
    console.log(`[CB] Trigger fired: ${variableName}`, data);
  } else {
    console.warn(`[CB] Trigger failed [${res.status}]:`, data);
  }
  return data;
}

// ────────────────────────────────────────────
// Main
// ────────────────────────────────────────────

window.addEventListener("load", async () => {
  try {
    const [consumerToken, variables] = await Promise.all([
      fetchConsumerToken(),
      fetchVariables(),
    ]);

    if (!consumerToken) {
      console.warn("[CB] Token nahi mila, tracker stop.");
      return;
    }
    if (!variables.length) {
      console.warn("[CB] Koi variables nahi mile.");
      return;
    }

    const clickables = document.querySelectorAll(
      "a, button, input[type=submit], input[type=button]",
    );
    console.log(
      `[CB] ${clickables.length} elements, ${variables.length} variables ready`,
    );

    clickables.forEach((el) => {
      el.addEventListener(
        "click",
        async () => {
          const matched = matchVariable(el, variables);
          if (!matched) return;
          await fireTrigger(matched.name, consumerToken);
        },
        true,
      );
    });
  } catch (err) {
    console.error("[CB] Tracker error:", err);
  }
});
