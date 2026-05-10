/**
 * CentreBlock Webflow Tracker
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
    console.log("[CB] Fetching token for uuid:", websiteDomain);

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
      console.log("[CB] Token received:", data.token.slice(0, 20) + "...");
      return data.token;
    }
    console.warn("[CB] Token failed:", data);
    return null;
  }

  // 2. Fetch Rules
  async function fetchRules() {
    console.log("[CB] Fetching rules...");
    var res = await fetch(BACKEND_URL + "/get_rules");
    var rules = await res.json();

    var currentHost = window.location.hostname.replace(/^www\./, "");
    var currentPath = window.location.pathname.replace(/\/+$/, "") || "/";
    console.log("[CB] Current host:", currentHost, "| path:", currentPath);

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
      "[CB] Total rules:",
      rules.length,
      "| Site rules:",
      siteRules.length,
    );
    siteRules.forEach(function (r) {
      console.log(
        "[CB] Rule:",
        r.cb_variable_name,
        "| page:",
        r.page_url,
        "| selector:",
        r.selector,
        "| text:",
        r.element_text,
      );
    });
    return siteRules;
  }

  // 3. Match element
  function matchRule(element, rules) {
    var currentPath = window.location.pathname.replace(/\/+$/, "") || "/";

    for (var i = 0; i < rules.length; i++) {
      var rule = rules[i];

      // Page check
      if (rule.page_url) {
        try {
          var rulePath =
            new URL(rule.page_url).pathname.replace(/\/+$/, "") || "/";
          if (rulePath !== currentPath) continue;
        } catch (e) {
          continue;
        }
      }

      var matched = false;

      // Strategy 1: #id selector
      if (rule.selector && rule.selector.startsWith("#")) {
        try {
          var el = document.querySelector(rule.selector);
          if (el && el === element) matched = true;
        } catch (e) {}
      }

      // Strategy 2: tag + text + class
      if (!matched && rule.element_text && rule.element_tag) {
        var elText = element.textContent.trim();
        var elTag = element.tagName.toLowerCase();
        if (
          elTag === rule.element_tag.toLowerCase() &&
          elText === rule.element_text.trim()
        ) {
          if (rule.element_classes) {
            var ruleFirstClass = rule.element_classes.split(" ")[0];
            if (element.classList.contains(ruleFirstClass)) matched = true;
          } else {
            matched = true;
          }
        }
      }

      // Strategy 3: nth-of-type manual count
      if (!matched && rule.selector && !rule.selector.startsWith("#")) {
        try {
          var selectorBase = rule.selector
            .replace(/:nth-of-type\(\d+\)/g, "")
            .replace(/:nth-child\(\d+\)/g, "");
          var nthMatch = rule.selector.match(/:nth-of-type\((\d+)\)/);
          var nthIndex = nthMatch ? parseInt(nthMatch[1]) - 1 : -1;

          if (nthIndex >= 0) {
            var candidates = document.querySelectorAll(selectorBase);
            console.log(
              "[CB] Strategy 3 — selector:",
              selectorBase,
              "| nth:",
              nthIndex,
              "| found:",
              candidates.length,
              "elements",
            );
            if (candidates[nthIndex] && candidates[nthIndex] === element)
              matched = true;
          } else {
            var els = document.querySelectorAll(selectorBase);
            for (var k = 0; k < els.length; k++) {
              if (els[k] === element) {
                matched = true;
                break;
              }
            }
          }
        } catch (e) {
          console.warn("[CB] Strategy 3 error:", e);
        }
      }

      if (matched) {
        console.log(
          "[CB] MATCHED:",
          element.textContent.trim(),
          "->",
          rule.cb_variable_name,
        );
        return rule;
      }
    }
    return null;
  }

  // 4. Fire Trigger
  async function fireTrigger(variableName, consumerToken) {
    if (!variableName) {
      console.warn("[CB] No variable name");
      return;
    }
    console.log("[CB] Firing trigger:", variableName);

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
    if (res.ok)
      console.log("[CB] Trigger fired successfully:", variableName, data);
    else console.warn("[CB] Trigger FAILED [" + res.status + "]:", data);
    return data;
  }

  // Main
  async function initTracker() {
    console.log("[CB] Tracker initializing...");
    try {
      var consumerToken = await fetchConsumerToken();
      var rules = await fetchRules();

      if (!consumerToken) {
        console.warn("[CB] No token — stopping");
        return;
      }
      if (!rules.length) {
        console.warn("[CB] No rules — stopping");
        return;
      }

      var clickables = document.querySelectorAll(
        "a, button, input[type=submit], input[type=button]",
      );
      console.log(
        "[CB] Attaching listeners to",
        clickables.length,
        "elements for",
        rules.length,
        "rules",
      );

      clickables.forEach(function (el) {
        el.addEventListener(
          "click",
          async function () {
            console.log(
              "[CB] Click detected on:",
              el.tagName,
              "|",
              el.textContent.trim().slice(0, 30),
            );
            var matched = matchRule(el, rules);
            if (!matched) {
              console.log("[CB] No rule matched for this element");
              return;
            }
            await fireTrigger(matched.cb_variable_name, consumerToken);
          },
          true,
        );
      });

      console.log("[CB] Tracker ready");
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
