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

  // 2. Fetch Rules — exact selector + variable name mapping
  async function fetchVariables() {
    var res = await fetch(BACKEND_URL + "/get_rules");
    var rules = await res.json();

    // Filter rules for current site
    var currentHost = window.location.hostname.replace(/^www\./, "");
    var siteRules = rules.filter(function (r) {
      if (!r.website_url) return false;
      try {
        var ruleHost = new URL(r.website_url).hostname.replace(/^www\./, "");
        return ruleHost === currentHost;
      } catch (e) {
        return false;
      }
    });

    console.log(
      "[CB] Rules: " +
        rules.length +
        " total, " +
        siteRules.length +
        ' for "' +
        currentHost +
        '"',
    );
    return siteRules;
  }

  // 3. Match element — exact selector match from rules
  function matchVariable(element, rules) {
    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];
      if (!rule.selector) continue;

      // Check if this element matches the rule selector
      try {
        var matched = document.querySelectorAll(rule.selector);
        for (var j = 0; j < matched.length; j++) {
          if (matched[j] === element) {
            console.log(
              '[CB] Match: "' +
                element.textContent.trim() +
                '" -> ' +
                rule.cb_variable_name,
            );
            return rule;
          }
        }
      } catch (e) {}
    }
    return null;
  }

  // 4. Fire Trigger
  async function fireTrigger(variableName, consumerToken) {
    if (!variableName) {
      console.warn("[CB] No variable name");
      return;
    }
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
            await fireTrigger(matched.cb_variable_name, consumerToken);
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
