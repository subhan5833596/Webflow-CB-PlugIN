const BACKEND_URL = "https://webflow-cb-plug-in.vercel.app/"; // Your backend URL

window.addEventListener("load", async () => {
  try {
    const rulesRes = await fetch(`${BACKEND_URL}/get_rules`);
    const rules = await rulesRes.json();
    const currentURL = window.location.href;
    const websiteURL = new URL(currentURL).origin;

    rules.forEach((rule) => {
      if (currentURL.includes(rule.page_url)) {
        try {
          const elements = document.querySelectorAll(rule.selector);

          if (!elements.length) {
            console.warn("⚠️ No elements matched:", rule.selector);
            return;
          }

          elements.forEach((el) => {
            const handleEvent = (e) => {
              console.log(`📌 Tracking: ${rule.action} on`, rule.selector);

              if (
                rule.action === "click" &&
                el.tagName === "INPUT" &&
                el.type === "submit"
              ) {
                e.preventDefault(); // Stop form submission
              }

              fetch(`${BACKEND_URL}/track_event`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  user: "anonymous",
                  website_url: websiteURL,
                  page_url: currentURL,
                  selector: rule.selector,
                  action: rule.action,
                  matched_rule: true,
                  timestamp: new Date().toISOString(),
                }),
              }).finally(() => {
                // If it was a submit button, submit form manually
                if (
                  rule.action === "click" &&
                  el.tagName === "INPUT" &&
                  el.type === "submit" &&
                  el.form
                ) {
                  el.form.submit();
                }
              });
            };

            el.addEventListener(rule.action, handleEvent, true); // Use capture phase
          });
        } catch (err) {
          console.error("❌ Error attaching rule:", rule, err);
        }
      }
    });
  } catch (err) {
    console.error("❌ Failed to fetch rules:", err);
  }
});
