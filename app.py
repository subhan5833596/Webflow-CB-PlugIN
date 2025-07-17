from datetime import datetime
from urllib.parse import urljoin, urlparse
import uuid
from flask import Flask, render_template, request, jsonify
import os
import json

app = Flask(__name__)

# Ensure data files exist
for f in ["rules.json", "events.json"]:
    if not os.path.exists(f):
        with open(f, "w") as file:
            json.dump([], file)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/tracking_rule")
def tracking_rule():
    return render_template("tracking_rule.html")

@app.route("/tracking_history")
def tracking_history():
    return render_template("tracking_history.html")

from bs4 import BeautifulSoup
import requests

@app.route("/get_elements")
def get_elements():
    page_url = request.args.get("page_url")
    if not page_url:
        return jsonify([])

    try:
        res = requests.get(page_url, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        elements = []

        for tag in soup.find_all(["a", "button", "input", "img", "div", "span"]):
            selector = get_selector(tag)
            name = (
                tag.get("aria-label") or
                tag.get("alt") or
                tag.get("placeholder") or
                tag.get("title") or
                tag.get("name") or
                tag.get("value") or
                tag.text or
                tag.get("href") or
                tag.get("src") or
                tag.get("id") or
                tag.get("class") or
                tag.name
            )

            if selector:
                elements.append({
                    "name": str(name).strip()[:60],
                    "selector": selector,
                    "tag": tag.name,
                    "id": tag.get("id", ""),
                    "classes": " ".join(tag.get("class", [])),
                    "text": tag.get_text(strip=True)
                })

        return jsonify(elements)

    except Exception as e:
        print("Error fetching elements:", e)
        return jsonify([])

def get_selector(tag):
    try:
        if tag.get("id"):
            return f"#{tag.get('id')}"

        path = []
        while tag and tag.name != "[document]":
            sibling_index = 1
            sibling = tag
            while sibling.previous_sibling:
                sibling = sibling.previous_sibling
                if sibling.name == tag.name:
                    sibling_index += 1

            segment = tag.name
            if tag.get("class"):
                segment += "." + ".".join(tag.get("class"))
            segment += f":nth-of-type({sibling_index})"

            path.insert(0, segment)
            tag = tag.parent

        return " > ".join(path)
    except Exception as e:
        print("Selector generation error:", e)
        return None


@app.route("/add_rule", methods=["POST"])
def add_rule():
    data = request.get_json()
    rule = {
        "rule_id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat() + "Z",
        "website_url": data["website_url"],
        "page_url": data["page_url"],
        "action": data["action"],
        "selector": data["selector"],
        "element_text": data.get("element_text", ""),
        "element_tag": data.get("element_tag", ""),
        "element_id": data.get("element_id", ""),
        "element_classes": data.get("element_classes", "")
    }

    try:
        with open("rules.json", "r") as f:
            rules = json.load(f)
    except FileNotFoundError:
        rules = []

    rules.append(rule)
    with open("rules.json", "w") as f:
        json.dump(rules, f, indent=2)

    return jsonify({"message": "Rule added", "rule": rule})

@app.route("/get_rules")
def get_rules():
    try:
        with open("rules.json", "r") as f:
            rules = json.load(f)
    except:
        rules = []
    return jsonify(rules)


@app.route("/track_event", methods=["POST"])
def track_event():
    try:
        data = request.get_json()
        with open("events.json", "r") as f:
            try:
                events = json.load(f)
            except:
                events = []

        events.append(data)
        with open("events.json", "w") as f:
            json.dump(events, f, indent=2)

        return jsonify({"message": "Event tracked successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_events")
def get_events():
    try:
        with open("events.json", "r") as f:
            try:
                events = json.load(f)
            except json.JSONDecodeError:
                events = []
    except FileNotFoundError:
        events = []
    return jsonify(events)

@app.route("/delete_rule/<int:index>", methods=["DELETE"])
def delete_rule(index):
    try:
        with open("rules.json", "r") as f:
            rules = json.load(f)

        if 0 <= index < len(rules):
            removed = rules.pop(index)
            with open("rules.json", "w") as f:
                json.dump(rules, f, indent=2)
            return jsonify({"message": f"Rule deleted for selector: {removed['selector']}"})
        else:
            return jsonify({"error": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/setup_page")
def setup_page():
    return render_template("setup.html")


@app.route("/setup", methods=["POST"])
def setup():
    data = request.get_json()
    site_url = data.get("webflow_url")

    # Extract pages from site
    try:
        res = requests.get(site_url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        from urllib.parse import urljoin

        pages = []
        for tag in soup.find_all("a", href=True):
            href = tag['href']
            if href.startswith("#") or "mailto:" in href or (href.startswith("http") and site_url not in href):
                continue
            full_url = urljoin(site_url, href)
            label = tag.get_text(strip=True) or full_url
            pages.append({
                "label": label[:40],
                "url": full_url
            })

        site_data = {
            "webflow_url": site_url,
            "pages": pages
        }

        with open("site_config.json", "w") as f:
            json.dump(site_data, f, indent=2)

        return jsonify({"message": "Setup saved", "pages": pages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get_site_config", methods=["GET"])
def get_site_config():
    if not os.path.exists("site_config.json"):
        return jsonify({})
    with open("site_config.json", "r") as f:
        return jsonify(json.load(f))


@app.route("/delete_site_config", methods=["DELETE"])
def delete_site_config():
    if os.path.exists("site_config.json"):
        os.remove("site_config.json")
        return jsonify({"message": "Site config deleted"})
    return jsonify({"message": "No config found"}), 404


@app.route("/extract_pages")
def extract_pages():
    site_url = request.args.get("site_url")

    if not site_url:
        return jsonify({"error": "Missing site_url"}), 400

    try:
        res = requests.get(site_url, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        links_seen = set()
        pages = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            # Skip invalid/irrelevant links
            if (
                href.startswith("#") or
                "mailto:" in href or
                "tel:" in href or
                href.startswith("javascript:")
            ):
                continue

            full_url = urljoin(site_url, href)
            parsed = urlparse(full_url)

            # Only include links from same domain
            if parsed.netloc != urlparse(site_url).netloc:
                continue

            if full_url in links_seen:
                continue
            links_seen.add(full_url)

            # Set label based on path only
            path = parsed.path.rstrip("/")
            label = "index" if path == "" or path == "/" else path.split("/")[-1]

            pages.append({
                "label": label,
                "url": full_url
            })
        print(pages)
        return jsonify(pages)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
