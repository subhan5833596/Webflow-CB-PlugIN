/**
 * CentreBlock Webflow Tracker
 */

(function () {
  var BACKEND_URL =
    "https://centreblock-webflow-tracker-h6c7c6c2bdawgeh4.canadacentral-01.azurewebsites.net";

  // 1. Consumer Token
  async function fetchConsumerToken() {
    var cached = sessionStorage.getItem("_cb_token");
    if (cached) return cached;

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
      console.log("[CB] Consumer token mila");
      return data.token;
    }
    console.warn("[CB] Token nahi mila:", data);
    return null;
  }

  // 2. CB Variables
  async function fetchVariables() {
    var cached = sessionStorage.getItem("_cb_variables");
    if (cached) return JSON.parse(cached);

    var res = await fetch(BACKEND_URL + "/cb_variables");
    var vars = await res.json();

    var domain = window.location.hostname.replace(/^www\./, "");
    var rawSite = domain
      .split(".")[0]
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "");
    var prefix = /^[a-z]/.test(rawSite) ? rawSite : "site";

    var filtered = vars.filter(function (v) {
      return v.name && v.name.startsWith(prefix + "_");
    });
    console.log(
      "[CB] Variables: " +
        vars.length +
        " total, " +
        filtered.length +
        ' for "' +
        prefix +
        '"',
    );

    sessionStorage.setItem("_cb_variables", JSON.stringify(filtered));
    return filtered;
  }

  // 3. Match element
  function matchVariable(element, variables) {
    var domain = window.location.hostname.replace(/^www\./, "");
    var rawSite = domain
      .split(".")[0]
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "");
    var siteName = /^[a-z]/.test(rawSite) ? rawSite : "site";

    var pathOnly = window.location.pathname.replace(/^\/|\/$/g, "");
    var slug =
      (pathOnly.split("/").pop() || "home")
        .toLowerCase()
        .replace(/[^a-z]/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_|_$/g, "") || "home";

    var text = (element.textContent || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 25);
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

    for (var i = 0; i < variables.length; i++) {
      var vname = variables[i].name || "";
      if (!vname.startsWith(siteName + "_")) continue;
      if (!vname.includes(slug)) continue;
      for (var j = 0; j < hints.length; j++) {
        if (hints[j] && vname.endsWith("_" + hints[j])) {
          console.log(
            '[CB] Match: "' + element.textContent.trim() + '" -> ' + vname,
          );
          return variables[i];
        }
      }
    }
    return null;
  }

  // 4. Fire Trigger
  async function fireTrigger(variableName, consumerToken) {
    console.log("[CB] Firing: " + variableName);
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
    if (res.ok) console.log("[CB] Trigger fired: " + variableName, data);
    else console.warn("[CB] Trigger failed [" + res.status + "]:", data);
    return data;
  }

  // Main
  async function initTracker() {
    try {
      var consumerToken = await fetchConsumerToken();
      var variables = await fetchVariables();

      if (!consumerToken) {
        console.warn("[CB] Token nahi mila, stop.");
        return;
      }
      if (!variables.length) {
        console.warn("[CB] Koi variables nahi mile.");
        return;
      }

      var clickables = document.querySelectorAll(
        "a, button, input[type=submit], input[type=button]",
      );
      console.log(
        "[CB] " +
          clickables.length +
          " elements, " +
          variables.length +
          " variables ready",
      );

      clickables.forEach(function (el) {
        el.addEventListener(
          "click",
          async function () {
            var matched = matchVariable(el, variables);
            if (!matched) return;
            await fireTrigger(matched.name, consumerToken);
          },
          true,
        );
      });
    } catch (err) {
      console.error("[CB] Tracker error:", err);
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
