/**
 * CentreBlock-via-server beacon.
 *
 * This script is intentionally DUMB. It contains:
 *   - NO CentreBlock URL
 *   - NO CentreBlock secret
 *   - NO list of variables
 *   - NO matching logic
 *   - NO knowledge of which clicks "count"
 *
 * It only does two things:
 *   1. Assign the visitor a stable random ID (stored in localStorage).
 *   2. On every click anywhere on the page, send the clicked element's
 *      selector + page URL to YOUR server.
 *
 * Your server decides whether the click matches a rule, looks up the
 * visitor's CB token, fires the CB trigger, etc. The browser learns
 * nothing it could leak.
 *
 * Install: in Webflow → Project Settings → Custom Code → Footer Code:
 *   <script src="https://YOUR-SERVER/beacon.js" defer></script>
 *
 * Or, if you want to be explicit about which server:
 *   <script>window.__CB_BEACON_URL = "https://YOUR-SERVER/api/beacon";</script>
 *   <script src="https://YOUR-SERVER/beacon.js" defer></script>
 */
(function () {
  "use strict";

  // ─── Configuration ────────────────────────────────────────────
  // By default, the beacon posts to /api/beacon on the SAME ORIGIN
  // it was loaded from. So if you serve beacon.js from
  // https://your-server.com/beacon.js, it posts to
  // https://your-server.com/api/beacon. You don't need to edit this.
  var BEACON_URL = (function () {
    if (window.__CB_BEACON_URL) return window.__CB_BEACON_URL;
    // Derive from this script's own src
    var scripts = document.getElementsByTagName("script");
    for (var i = scripts.length - 1; i >= 0; i--) {
      var src = scripts[i].src || "";
      if (src.indexOf("/beacon.js") !== -1) {
        return src.replace(/\/beacon\.js.*$/, "/api/beacon");
      }
    }
    return "/api/beacon"; // last-resort fallback
  })();

  // ─── Visitor ID (stable per browser) ──────────────────────────
  var VISITOR_KEY = "_cb_visitor";
  function getVisitorId() {
    try {
      var id = localStorage.getItem(VISITOR_KEY);
      if (id) return id;
      // Random 16-byte hex
      var arr = new Uint8Array(16);
      (window.crypto || window.msCrypto).getRandomValues(arr);
      id = Array.prototype.map
        .call(arr, function (b) { return ("0" + b.toString(16)).slice(-2); })
        .join("");
      localStorage.setItem(VISITOR_KEY, id);
      return id;
    } catch (e) {
      // localStorage blocked — fall back to ephemeral per-page id
      return "ephemeral_" + Math.random().toString(36).slice(2);
    }
  }

  // ─── Build a selector for a clicked element ───────────────────
  // Matches the format the scraper uses on the server:
  //   #id          (if id present)
  //   tag.class:nth-of-type(N)
  //   tag:nth-of-type(N)
  function selectorFor(el) {
    if (!el || !el.tagName) return "";
    if (el.id) return "#" + el.id;
    var tag = el.tagName.toLowerCase();
    var firstClass = (el.classList && el.classList[0]) || "";
    // nth-of-type index among siblings of same tag in the *whole document*
    // (matches server-side scraper's behavior, which counts across the page).
    var all = document.getElementsByTagName(tag);
    var idx = 0;
    for (var i = 0; i < all.length; i++) {
      if (all[i] === el) { idx = i; break; }
    }
    if (firstClass) return tag + "." + firstClass + ":nth-of-type(" + (idx + 1) + ")";
    return tag + ":nth-of-type(" + (idx + 1) + ")";
  }

  // ─── Find the nearest clickable ancestor ──────────────────────
  // If the user clicks the <span> inside a <button>, we want the <button>.
  function nearestClickable(el) {
    var CLICKABLE = { A: 1, BUTTON: 1, INPUT: 1 };
    while (el && el !== document) {
      if (el.tagName && CLICKABLE[el.tagName.toUpperCase()]) return el;
      el = el.parentElement;
    }
    return null;
  }

  // ─── Send the beacon ──────────────────────────────────────────
  function send(selector) {
    var payload = JSON.stringify({
      selector: selector,
      page_url: window.location.href,
      visitor_id: getVisitorId(),
    });

    // sendBeacon is ideal — it works even on navigation away.
    // Falls back to fetch with keepalive if not available.
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([payload], { type: "application/json" });
        if (navigator.sendBeacon(BEACON_URL, blob)) return;
      }
    } catch (e) { /* fall through */ }

    try {
      fetch(BEACON_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
        mode: "cors",
        credentials: "omit",
      }).catch(function () { /* swallow */ });
    } catch (e) { /* nothing else we can do */ }
  }

  // ─── Wire up the click listener ───────────────────────────────
  function onClick(e) {
    var el = nearestClickable(e.target);
    if (!el) return;
    var sel = selectorFor(el);
    if (!sel) return;
    send(sel);
    // We do NOT prevent default or intercept navigation. The server
    // either records the click or it doesn't — the user's experience
    // on the Webflow site is unaffected.
  }

  // Capture phase so we record the click even if Webflow's own
  // interactions stop propagation later.
  document.addEventListener("click", onClick, true);
})();
