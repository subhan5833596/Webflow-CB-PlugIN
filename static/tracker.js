/**
 * CentreBlock Webflow Tracker
 * No rules needed — matches directly from CB variables
 */

(function () {
  var BACKEND_URL =
    "https://centreblock-webflow-tracker-h6c7c6c2bdawgeh4.canadacentral-01.azurewebsites.net";

  // 1. Consumer Token
  async function fetchConsumerToken() {
    var cached = sessionStorage.getItem("_cb_token");
    if (cached) {
      console.log("[CB] Token from cache");
      return cached;
    }

    var websiteDomain = window.location.host.replace(":", "_");
    var res = await fetch(BACKEND_URL + "/get_consumer_token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        uuid: websiteDomain,
        entry_page: window.location.href,
        referer: document.referrer || "",
        audiences: ["default"],
      }),
    });

    var data = await res.json();
    if (data.token) {
      sessionStorage.setItem("_cb_token", data.token);
      console.log("[CB] Token received");
      return data.token;
    }
    console.warn("[CB] Token failed:", data);
    return null;
  }

  // 2. Fetch CB Variables — filter by site + current page
  async function fetchVariables() {
    var res = await fetch(BACKEND_URL + "/cb_variables");
    var vars = await res.json();
    if (!Array.isArray(vars)) {
      console.warn("[CB] Variables error:", vars);
      return [];
    }

    // Site name from domain
    var domain = window.location.hostname.replace(/^www\./, "");
    var rawSite = domain
      .split(".")[0]
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "");
    var siteName = /^[a-z]/.test(rawSite) ? rawSite : "site";

    // Page slug
    var pathOnly = window.location.pathname.replace(/^\/|\/$/g, "");
    var rawSlug = pathOnly.split("/").pop() || "home";
    if (!rawSlug || rawSlug.toLowerCase().startsWith("index")) rawSlug = "home";
    var slug =
      rawSlug
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_|_$/g, "") || "home";

    // Filter: site prefix + page slug in name
    var prefix = siteName + "_";
    var pageKey = siteName + "_" + slug + "_";

    // Deduplicate by name (CSV returns one row per category)
    var seen = {};
    vars.forEach(function (v) {
      if (v.name) seen[v.name] = v;
    });
    var unique = Object.values(seen);

    var siteVars = unique.filter(function (v) {
      return v.name && v.name.startsWith(prefix);
    });
    var pageVars = unique.filter(function (v) {
      return v.name && v.name.startsWith(pageKey);
    });

    console.log("[CB] Site:", siteName, "| Slug:", slug);
    console.log(
      "[CB] Total vars:",
      vars.length,
      "| Site vars:",
      siteVars.length,
      "| Page vars:",
      pageVars.length,
    );
    pageVars.forEach(function (v) {
      console.log("[CB]  -", v.name);
    });

    // Use page vars if available, else all site vars
    return pageVars.length ? pageVars : siteVars;
  }

  // 3. Match clicked element to a variable
  function matchVariable(element, variables) {
    // Build hints from element
    var text = (element.textContent || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 30);
    var id = (element.id || "")
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 25);
    var cls =
      element.classList && element.classList[0]
        ? element.classList[0]
            .toLowerCase()
            .replace(/[^a-z]/g, "_")
            .replace(/_+/g, "_")
            .replace(/^_|_$/g, "")
        : "";

    var hints = [text, id, cls].filter(Boolean);
    console.log("[CB] Click hints:", hints);

    for (var i = 0; i < variables.length; i++) {
      var vname = variables[i].name || "";
      for (var j = 0; j < hints.length; j++) {
        if (hints[j] && vname.endsWith("_" + hints[j])) {
          console.log("[CB] MATCHED:", element.textContent.trim(), "->", vname);
          return variables[i];
        }
      }
    }
    console.log("[CB] No match for:", element.textContent.trim().slice(0, 30));
    return null;
  }

  // 4. Fire Trigger
  async function fireTrigger(variableName, consumerToken) {
    console.log("[CB] Firing:", variableName);
    var res = await fetch(BACKEND_URL + "/fire_trigger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variable_name: variableName,
        consumer_token: consumerToken,
        page: window.location.href,
        direction: "Neutral",
      }),
    });
    var data = await res.json().catch(function () {
      return {};
    });
    if (res.ok) console.log("[CB] Trigger fired:", variableName, data);
    else console.warn("[CB] Trigger FAILED [" + res.status + "]:", data);
    return data;
  }

  // Main
  async function initTracker() {
    console.log("[CB] Initializing...");
    try {
      var consumerToken = await fetchConsumerToken();
      var variables = await fetchVariables();

      if (!consumerToken) {
        console.warn("[CB] No token — stopping");
        return;
      }
      if (!variables.length) {
        console.warn("[CB] No variables for this page");
        return;
      }

      var clickables = document.querySelectorAll(
        "a, button, input[type=submit], input[type=button]",
      );
      console.log(
        "[CB] Ready —",
        clickables.length,
        "elements,",
        variables.length,
        "variables",
      );

      clickables.forEach(function (el) {
        el.addEventListener(
          "click",
          async function (e) {
            var matched = matchVariable(el, variables);
            if (!matched) return;

            // Stop navigation briefly so trigger can fire
            var href = el.getAttribute("href");
            var isLink =
              el.tagName.toLowerCase() === "a" &&
              href &&
              !href.startsWith("#") &&
              href !== "javascript:void(0)";

            if (isLink) {
              e.preventDefault();
              e.stopPropagation();
            }

            await fireTrigger(matched.name, consumerToken);

            // Resume navigation after trigger
            if (isLink) {
              if (el.target === "_blank") {
                window.open(href, "_blank");
              } else {
                window.location.href = href;
              }
            }
          },
          true,
        );
      });
    } catch (err) {
      console.error("[CB] Error:", err);
    }
  }

  if (
    document.readyState === "complete" ||
    document.readyState === "interactive"
  ) {
    initTracker();
  } else {
    window.addEventListener("DOMContentLoaded", initTracker);
  }
})();
