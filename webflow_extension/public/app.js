/**
 * CentreBlock Tracker — Webflow Designer Extension
 *
 * IMPORTANT difference from the standalone version:
 *   When this runs inside Webflow, the iframe is hosted on a *.webflow-ext.com
 *   URL, NOT on your backend's domain. So we can't derive the API base from
 *   window.location.origin. The user must enter their backend URL once on
 *   first run; we save it in the Designer's extension storage.
 *
 * It STILL never talks to CentreBlock directly. It only talks to YOUR backend.
 */
(function () {
  "use strict";

  // ─── Webflow Designer SDK ─────────────────────────────────
  // Inside the Designer, `window.webflow` is injected automatically.
  // Outside (local dev in plain browser), it's undefined — we fall back to localStorage.
  var wf = window.webflow;

  // ─── Persistent config (backend URL + admin token) ────────
  var CONFIG_KEYS = { url: "cb_backend_url", token: "cb_admin_token" };

  async function getConfig() {
    if (wf && wf.getExtensionElement) {
      // Newer SDK uses extensionStorage; fall back gracefully
      try {
        var url = await wf.getExtensionStorageItem(CONFIG_KEYS.url);
        var token = await wf.getExtensionStorageItem(CONFIG_KEYS.token);
        return { url: url || "", token: token || "" };
      } catch (e) { /* fall through */ }
    }
    return {
      url: localStorage.getItem(CONFIG_KEYS.url) || "",
      token: localStorage.getItem(CONFIG_KEYS.token) || "",
    };
  }

  async function setConfig(url, token) {
    if (wf && wf.setExtensionStorageItem) {
      try {
        await wf.setExtensionStorageItem(CONFIG_KEYS.url, url);
        await wf.setExtensionStorageItem(CONFIG_KEYS.token, token);
        return;
      } catch (e) { /* fall through */ }
    }
    localStorage.setItem(CONFIG_KEYS.url, url);
    localStorage.setItem(CONFIG_KEYS.token, token);
  }

  // ─── API helper ───────────────────────────────────────────
  var config = { url: "", token: "" };

  function headers(extra) {
    var h = { "Content-Type": "application/json" };
    if (config.token) h["Authorization"] = "Bearer " + config.token;
    return Object.assign(h, extra || {});
  }

  async function api(path, opts) {
    if (!config.url) {
      throw new Error("Backend URL not configured. Set it in Setup tab.");
    }
    opts = opts || {};
    opts.headers = headers(opts.headers);
    var res = await fetch(config.url.replace(/\/$/, "") + path, opts);
    var body = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      var msg = body.error || ("HTTP " + res.status);
      if (body.details) msg += " — " + body.details;
      throw new Error(msg);
    }
    return body;
  }

  // ─── State ────────────────────────────────────────────────
  var state = {
    sites: [], selectedSiteId: null,
    pages: [], selectedPage: null,
    elements: [], rules: [],
  };

  // ─── Tab switching ────────────────────────────────────────
  document.querySelectorAll(".tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".tab").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      document.querySelectorAll(".view").forEach(function (v) { v.classList.remove("active"); });
      document.getElementById("view-" + btn.dataset.view).classList.add("active");
      if (btn.dataset.view === "rules") refreshRulesView();
      if (btn.dataset.view === "install") renderInstall();
    });
  });

  function status(id, msg, kind) {
    var el = document.getElementById(id);
    el.textContent = msg || "";
    el.className = "status" + (kind ? " " + kind : "");
  }

  // ─── Backend config form ──────────────────────────────────
  document.getElementById("save-config").addEventListener("click", async function () {
    var url = document.getElementById("server-url").value.trim();
    var token = document.getElementById("admin-token").value.trim();
    if (!url) { status("site-status", "Backend URL is required.", "error"); return; }
    config.url = url;
    config.token = token;
    await setConfig(url, token);
    status("site-status", "Backend config saved. Loading sites…", "success");
    await loadSites();
  });

  // ─── SETUP VIEW ───────────────────────────────────────────
  async function loadSites() {
    if (!config.url) return;
    try {
      state.sites = await api("/api/sites");
      renderSites();
    } catch (e) {
      status("site-status", e.message, "error");
    }
  }

  function renderSites() {
    var list = document.getElementById("sites-list");
    if (!state.sites.length) {
      list.innerHTML = '<p class="muted">No sites configured yet.</p>';
      return;
    }
    list.innerHTML = state.sites.map(function (s) {
      return (
        '<div class="card">' +
          '<div class="meta">' +
            '<div class="name">' + escapeHtml(s.name || s.origin) + '</div>' +
            '<div class="sub">' + escapeHtml(s.origin) + ' · CB customer ' + s.cb_customer_id +
              (s.has_secret ? ' · 🔒 secret saved' : ' · ⚠ no secret') +
            '</div>' +
          '</div>' +
          '<div class="row">' +
            '<button class="btn small" data-edit="' + s.site_id + '">Edit</button>' +
            '<button class="btn small danger" data-del="' + s.site_id + '">Delete</button>' +
          '</div>' +
        '</div>'
      );
    }).join("");

    list.querySelectorAll("[data-edit]").forEach(function (b) {
      b.addEventListener("click", function () { editSite(b.dataset.edit); });
    });
    list.querySelectorAll("[data-del]").forEach(function (b) {
      b.addEventListener("click", function () { deleteSite(b.dataset.del); });
    });
  }

  function editSite(siteId) {
    var s = state.sites.find(function (x) { return x.site_id === siteId; });
    if (!s) return;
    var f = document.getElementById("site-form");
    f.elements["site_id"].value = s.site_id;
    f.elements["name"].value = s.name || "";
    f.elements["origin"].value = s.origin || "";
    f.elements["cb_customer_id"].value = s.cb_customer_id || "";
    f.elements["cb_secret"].value = "";
    document.getElementById("site-form-title").textContent = "Edit site";
  }

  async function deleteSite(siteId) {
    if (!confirm("Delete this site and all its rules?")) return;
    try {
      await api("/api/sites/" + siteId, { method: "DELETE" });
      await loadSites();
      status("site-status", "Site deleted.", "success");
    } catch (e) {
      status("site-status", e.message, "error");
    }
  }

  document.getElementById("site-form-cancel").addEventListener("click", function () {
    var f = document.getElementById("site-form");
    f.reset();
    f.elements["site_id"].value = "";
    document.getElementById("site-form-title").textContent = "Add a new site";
    status("site-status", "");
  });

  document.getElementById("site-form").addEventListener("submit", async function (ev) {
    ev.preventDefault();
    var f = ev.target;
    var siteId = f.elements["site_id"].value;
    var payload = {
      name: f.elements["name"].value.trim(),
      origin: f.elements["origin"].value.trim().replace(/\/$/, ""),
      cb_customer_id: f.elements["cb_customer_id"].value,
    };
    var secret = f.elements["cb_secret"].value.trim();
    if (secret) payload.cb_secret = secret;

    status("site-status", "Verifying credentials with CentreBlock…");
    try {
      if (siteId) {
        await api("/api/sites/" + siteId, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        if (!secret) throw new Error("CB secret is required for a new site.");
        await api("/api/sites", { method: "POST", body: JSON.stringify(payload) });
      }
      f.reset();
      f.elements["site_id"].value = "";
      document.getElementById("site-form-title").textContent = "Add a new site";
      status("site-status", "Saved. ✓", "success");
      await loadSites();
      populateRulesSiteSelect();
    } catch (e) {
      status("site-status", e.message, "error");
    }
  });

  // ─── RULES VIEW ───────────────────────────────────────────
  function populateRulesSiteSelect() {
    var sel = document.getElementById("rules-site-select");
    if (!state.sites.length) {
      sel.innerHTML = '<option value="">No sites — add one in Setup</option>';
      return;
    }
    sel.innerHTML = state.sites.map(function (s) {
      return '<option value="' + s.site_id + '">' +
        escapeHtml(s.name || s.origin) + '</option>';
    }).join("");
    if (!state.selectedSiteId) state.selectedSiteId = state.sites[0].site_id;
    sel.value = state.selectedSiteId;
  }

  document.getElementById("rules-site-select").addEventListener("change", function (ev) {
    state.selectedSiteId = ev.target.value;
    state.pages = []; state.elements = [];
    document.getElementById("pages-card").hidden = true;
    loadRules();
  });

  document.getElementById("discover-pages").addEventListener("click", async function () {
    var site = currentSite();
    if (!site) return;
    status("rules-status", "Discovering pages on " + site.origin + "…");
    try {
      var pages = await api("/api/discover/pages?site_url=" + encodeURIComponent(site.origin));
      state.pages = pages || [];
      renderPages();
      document.getElementById("pages-card").hidden = false;
      status("rules-status", "Found " + state.pages.length + " pages.", "success");
    } catch (e) {
      status("rules-status", e.message, "error");
    }
  });

  document.getElementById("reload-rules").addEventListener("click", loadRules);

  function currentSite() {
    return state.sites.find(function (s) { return s.site_id === state.selectedSiteId; }) || null;
  }

  function renderPages() {
    var html = state.pages.map(function (p) {
      var active = state.selectedPage && state.selectedPage.url === p.url ? " active" : "";
      return '<button class="chip' + active + '" data-url="' + escapeAttr(p.url) + '">' +
        escapeHtml(p.label || p.url) + '</button>';
    }).join("");
    var container = document.getElementById("pages-list");
    container.innerHTML = html;
    container.querySelectorAll(".chip").forEach(function (c) {
      c.addEventListener("click", function () { selectPage(c.dataset.url); });
    });
  }

  async function selectPage(url) {
    state.selectedPage = state.pages.find(function (p) { return p.url === url; }) || { url: url, label: url };
    renderPages();
    status("rules-status", "Discovering elements on " + url + "…");
    try {
      var els = await api("/api/discover/elements?page_url=" + encodeURIComponent(url));
      state.elements = els || [];
      renderElements();
      status("rules-status", "Found " + state.elements.length + " elements.", "success");
    } catch (e) {
      status("rules-status", e.message, "error");
    }
  }

  function renderElements() {
    document.getElementById("elements-title").hidden = !state.elements.length;
    var html = state.elements.map(function (el, idx) {
      var label = el.text || el.id || el.classes || "(element " + idx + ")";
      return (
        '<div class="element">' +
          '<div class="info">' +
            '<div class="txt">&lt;' + el.tag + '&gt; ' + escapeHtml(label) + '</div>' +
            '<div class="sel">' + escapeHtml(el.selector) + '</div>' +
          '</div>' +
          '<button class="btn small primary" data-idx="' + idx + '">Track</button>' +
        '</div>'
      );
    }).join("");
    var container = document.getElementById("elements-list");
    container.innerHTML = html;
    container.querySelectorAll("[data-idx]").forEach(function (b) {
      b.addEventListener("click", function () { addRuleForElement(parseInt(b.dataset.idx, 10)); });
    });
  }

  async function addRuleForElement(idx) {
    var el = state.elements[idx];
    if (!el || !state.selectedPage) return;
    var site = currentSite();
    if (!site) return;
    var direction = prompt("Direction (Positive / Negative / Neutral):", "Positive");
    if (!direction) return;
    status("rules-status", "Creating rule and CB variable…");
    try {
      var result = await api("/api/rules", {
        method: "POST",
        body: JSON.stringify({
          site_id: site.site_id,
          page_url: state.selectedPage.url,
          selector: el.selector,
          action: "click",
          element_text: el.text,
          element_tag: el.tag,
          element_id: el.id,
          element_classes: el.classes,
          direction: direction,
          weight_customer: 15,
          weight_default: 15,
          leaving_link: el.href && el.href.startsWith("http") && !el.href.startsWith(site.origin) ? el.href : "",
        }),
      });
      if (result.cb_error) {
        status("rules-status", "Rule saved, but CB variable failed: " + result.cb_error, "error");
      } else {
        status("rules-status", "Rule added → CB variable: " + (result.rule.cb_variable_name), "success");
      }
      await loadRules();
    } catch (e) {
      status("rules-status", e.message, "error");
    }
  }

  async function loadRules() {
    if (!state.selectedSiteId) {
      document.getElementById("rules-list").innerHTML = '<p class="muted">Select a site first.</p>';
      return;
    }
    try {
      state.rules = await api("/api/rules?site_id=" + state.selectedSiteId);
      renderRules();
    } catch (e) {
      status("rules-status", e.message, "error");
    }
  }

  function renderRules() {
    var list = document.getElementById("rules-list");
    if (!state.rules.length) {
      list.innerHTML = '<p class="muted">No rules yet. Discover pages and click "Track" on an element.</p>';
      return;
    }
    list.innerHTML = state.rules.map(function (r) {
      return (
        '<div class="rule">' +
          '<div class="info">' +
            '<div class="name">' + escapeHtml(r.cb_variable_name) + '</div>' +
            '<div class="sub">' + escapeHtml(r.page_url || "(any page)") +
              ' · ' + escapeHtml(r.selector) + '</div>' +
          '</div>' +
          '<button class="btn small danger" data-rule-del="' + r.rule_id + '">Delete</button>' +
        '</div>'
      );
    }).join("");
    list.querySelectorAll("[data-rule-del]").forEach(function (b) {
      b.addEventListener("click", async function () {
        if (!confirm("Delete this rule? (The CB variable in CentreBlock will not be deleted.)")) return;
        try {
          await api("/api/rules/" + b.dataset.ruleDel, { method: "DELETE" });
          await loadRules();
        } catch (e) {
          status("rules-status", e.message, "error");
        }
      });
    });
  }

  function refreshRulesView() {
    populateRulesSiteSelect();
    loadRules();
  }

  // ─── INSTALL VIEW ─────────────────────────────────────────
  function renderInstall() {
    if (!config.url) {
      document.getElementById("beacon-snippet").innerHTML =
        "<code>(configure backend URL in Setup first)</code>";
      return;
    }
    var snippet = '<script src="' + config.url.replace(/\/$/, "") + '/beacon.js" defer><\/script>';
    document.getElementById("beacon-snippet").innerHTML =
      "<code>" + escapeHtml(snippet) + "</code>";
  }

  // ─── Helpers ──────────────────────────────────────────────
  function escapeHtml(s) {
    s = String(s == null ? "" : s);
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function escapeAttr(s) { return escapeHtml(s); }

  // ─── Boot ─────────────────────────────────────────────────
  (async function () {
    config = await getConfig();
    if (config.url) document.getElementById("server-url").value = config.url;
    if (config.token) document.getElementById("admin-token").value = config.token;
    await loadSites();
    populateRulesSiteSelect();
  })();
})();
