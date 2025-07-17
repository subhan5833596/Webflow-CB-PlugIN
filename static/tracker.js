document.addEventListener("DOMContentLoaded", async () => {
  try {
    const rulesRes = await fetch("/get_rules");
    const rules = await rulesRes.json();
    const currentURL = window.location.href;
    const websiteURL = new URL(currentURL).origin;

    rules.forEach((rule) => {
      if (currentURL.includes(rule.page_url)) {
        try {
          const elements = document.querySelectorAll(rule.selector);
          if (!elements.length) {
            console.warn("⚠️ No elements matched:", rule.selector);
          }

          elements.forEach((el) => {
            const track = () => {
              fetch("/track_event", {
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
              });
            };

            el.addEventListener(rule.action, track, true);
          });
        } catch (err) {
          console.error("Failed to attach:", rule, err);
        }
      }
    });
  } catch (err) {
    console.error("Failed to fetch rules:", err);
  }
});
