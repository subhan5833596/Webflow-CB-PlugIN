document.addEventListener("DOMContentLoaded", () => {
  const selectorDropdown = document.getElementById("selector");
  const pageUrlSelect = document.getElementById("page-url");
  const form = document.getElementById("tracking-form");

  const elText = document.getElementById("element-text");
  const elTag = document.getElementById("element-tag");
  const elId = document.getElementById("element-id");
  const elClasses = document.getElementById("element-classes");

  // When element is selected → populate readonly fields
  selectorDropdown.addEventListener("change", () => {
    const selected = selectorDropdown.selectedOptions[0];
    elText.value = selected.dataset.text || "";
    elTag.value = selected.dataset.tag || "";
    elId.value = selected.dataset.id || "";
    elClasses.value = selected.dataset.classes || "";
  });

  // Load example pages based on entered website URL
  async function loadPages() {
    const siteUrl = document.getElementById("website-url").value.trim();

    if (!siteUrl) {
      alert("Please enter a website URL first.");
      return;
    }

    const res = await fetch(
      `/extract_pages?site_url=${encodeURIComponent(siteUrl)}`
    );
    const pages = await res.json();

    pageUrlSelect.innerHTML = "";

    pages.forEach((p) => {
      const option = document.createElement("option");
      option.value = p.url;
option.textContent = p.label; // 👈 use label instead of url.split

      pageUrlSelect.appendChild(option);
    });

    if (pages.length > 0) {
      fetchElements(pages[0].url); // Auto-load first page
    }
  }

  // Fetch elements for selected page
  async function fetchElements(url) {
    const res = await fetch(
      `/get_elements?page_url=${encodeURIComponent(url)}`
    );
    const elements = await res.json();
    selectorDropdown.innerHTML = "";

    // elements.forEach((el, index) => {
    //   const opt = document.createElement("option");
    //   opt.value = el.selector;

    //   const displaySelector =
    //     el.selector.length > 60
    //       ? el.selector.slice(0, 60) + "..."
    //       : el.selector;

    //   opt.textContent = `${el.name} [${displaySelector}]`;

    //   // ✅ Add dataset fields for selection display
    //   opt.dataset.index = index;
    //   opt.dataset.selector = el.selector;
    //   opt.dataset.text = el.name;
    //   opt.dataset.tag = el.tag;
    //   opt.dataset.id = el.id;
    //   opt.dataset.classes = el.classes;

    //   selectorDropdown.appendChild(opt);
    // });
  elements.forEach((el, index) => {
  const opt = document.createElement("option");
  opt.value = el.selector;

  // ✅ Priority based label
  let displayParts = [];
  if (el.text) displayParts.push(`Text: "${el.text}"`);
  if (el.tag) displayParts.push(`Tag: <${el.tag}>`);
  if (el.name) displayParts.push(`Name: ${el.name}`);
  if (el.id) displayParts.push(`ID: ${el.id}`);
  if (el.classes) displayParts.push(`Class: ${el.classes}`);
  if (el.selector) displayParts.push(`Selector: ${el.selector.slice(0, 60)}...`);

  opt.textContent = displayParts.join(" | ");

  // ✅ Add dataset for later use
  opt.dataset.index = index;
  opt.dataset.selector = el.selector;
  opt.dataset.text = el.text;
  opt.dataset.tag = el.tag;
  opt.dataset.name = el.name;
  opt.dataset.id = el.id;
  opt.dataset.classes = el.classes;

  selectorDropdown.appendChild(opt);
});

    if (elements.length > 0) {
      selectorDropdown.selectedIndex = 0;
      selectorDropdown.dispatchEvent(new Event("change"));
    }
  }

  // Change handler for Page URL dropdown
  pageUrlSelect.addEventListener("change", (e) => {
    const selectedURL = e.target.value;
    fetchElements(selectedURL);
  });

  // Handle form submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = {
      website_url: document.getElementById("website-url").value,
      page_url: pageUrlSelect.value,
      selector: selectorDropdown.value,
      action: document.getElementById("action").value,
      element_text: elText.value,
      element_tag: elTag.value,
      element_id: elId.value,
      element_classes: elClasses.value,
    };

    const res = await fetch("/add_rule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    const result = await res.json();
    alert(result.message || "Tracking rule added!");
    loadRulesTable();
  });

  // Load existing rules in the table
  async function loadRulesTable() {
    const res = await fetch("/get_rules");
    const rules = await res.json();
    const tableBody = document.getElementById("rules-table-body");
    tableBody.innerHTML = "";

    rules.forEach((rule, index) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${rule.website_url}</td>
        <td>${rule.page_url}</td>
        <td>${rule.action}</td>
        <td title="${rule.selector}">${rule.selector.slice(0, 40)}...</td>
        <td>${rule.timestamp}</td>
        <td><button onclick="deleteRule(${index})">Delete</button></td>
      `;
      tableBody.appendChild(row);
    });
  }

  // Delete rule by index
  async function deleteRule(index) {
    const confirmed = confirm("Are you sure you want to delete this rule?");
    if (!confirmed) return;

    const res = await fetch(`/delete_rule/${index}`, {
      method: "DELETE",
    });

    const result = await res.json();
    alert(result.message);
    loadRulesTable();
  }

  // Trigger page load manually when button is clicked
  document.getElementById("website-url").addEventListener("change", loadPages);

  // Load rules on page load
  loadRulesTable();
});
