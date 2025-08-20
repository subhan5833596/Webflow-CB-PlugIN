from datetime import datetime
from urllib.parse import urljoin, urlparse
import uuid
from flask import Flask, render_template, request, jsonify
import os
import json
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


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

# @app.route("/get_elements")
# def get_elements():
#     page_url = request.args.get("page_url")
#     if not page_url:
#         return jsonify([])

#     try:
#         res = requests.get(page_url, timeout=5)
#         soup = BeautifulSoup(res.text, "html.parser")
#         elements = []

#         for tag in soup.find_all(["a", "button", "input", "img", "div", "span"]):
#             selector = get_selector(tag)
#             name = (
#                 tag.get("aria-label") or
#                 tag.get("alt") or
#                 tag.get("placeholder") or
#                 tag.get("title") or
#                 tag.get("name") or
#                 tag.get("value") or
#                 tag.text or
#                 tag.get("href") or
#                 tag.get("src") or
#                 tag.get("id") or
#                 tag.get("class") or
#                 tag.name
#             )

#             if selector:
#                 elements.append({
#                     "name": str(name).strip()[:60],
#                     "selector": selector,
#                     "tag": tag.name,
#                     "id": tag.get("id", ""),
#                     "classes": " ".join(tag.get("class", [])),
#                     "text": tag.get_text(strip=True)
#                 })

#         return jsonify(elements)

#     except Exception as e:
#         print("Error fetching elements:", e)
#         return jsonify([])

# def get_selector(tag):
#     try:
#         if tag.get("id"):
#             return f"#{tag.get('id')}"

#         path = []
#         while tag and tag.name != "[document]":
#             sibling_index = 1
#             sibling = tag
#             while sibling.previous_sibling:
#                 sibling = sibling.previous_sibling
#                 if sibling.name == tag.name:
#                     sibling_index += 1

#             segment = tag.name
#             if tag.get("class"):
#                 segment += "." + ".".join(tag.get("class"))
#             segment += f":nth-of-type({sibling_index})"

#             path.insert(0, segment)
#             tag = tag.parent

#         return " > ".join(path)
#     except Exception as e:
#         print("Selector generation error:", e)
#         return None

# @app.route("/get_elements")
# def get_elements():
#     page_url = request.args.get("page_url")
#     if not page_url:
#         return jsonify([])

#     try:
#         res = requests.get(page_url, timeout=5)
#         res.raise_for_status()
#         soup = BeautifulSoup(res.text, "html.parser")
#         elements = []

#         # ✅ Sirf required tags: buttons, links, forms, inputs, images, videos
#         target_tags = ["a", "button", "form", "input", "img", "video"]

#         for tag in soup.find_all(target_tags):
#             selector = get_selector(tag)
#             if not selector:
#                 continue

#             # Human readable name
#             name = (
#                 tag.get("aria-label") or
#                 tag.get("alt") or
#                 tag.get("placeholder") or
#                 tag.get("title") or
#                 tag.get("name") or
#                 tag.get("value") or
#                 tag.get("href") or
#                 tag.get("src") or
#                 tag.get("id") or
#                 " ".join(tag.get("class", [])) or
#                 tag.name
#             )

#             elements.append({
#                 "name": str(name).strip()[:60],
#                 "selector": selector,
#                 "tag": tag.name,
#                 "id": tag.get("id", ""),
#                 "classes": " ".join(tag.get("class", [])),
#                 "text": tag.get_text(strip=True)
#             })

#         return jsonify(elements)

#     except Exception as e:
#         print("Error fetching elements:", e)
#         return jsonify([])


# def get_selector(tag):
#     """Generate CSS selector for element"""
#     try:
#         # If ID exists → use directly
#         if tag.get("id"):
#             return f"#{tag.get('id')}"

#         path = []
#         while tag and tag.name != "[document]":
#             sibling_index = 1
#             sibling = tag
#             while sibling.previous_sibling:
#                 sibling = sibling.previous_sibling
#                 if sibling.name == tag.name:
#                     sibling_index += 1

#             segment = tag.name
#             if tag.get("class"):
#                 segment += "." + ".".join(tag.get("class"))
#             segment += f":nth-of-type({sibling_index})"

#             path.insert(0, segment)
#             tag = tag.parent

#         return " > ".join(path)
#     except Exception as e:
#         print("Selector generation error:", e)
#         return None

# Static folder path for elements.json
ELEMENTS_FILE = os.path.join(app.root_path, "static", "elements.json")


@app.route("/get_elements")
def get_elements():
    page_url = request.args.get("page_url")
    web_url = request.args.get("web_url")  # base website URL
    if not page_url or not web_url:
        return jsonify({"error": "Missing page_url or web_url"}), 400

    # Load existing elements.json
    data = {}
    if os.path.exists(ELEMENTS_FILE):
        with open(ELEMENTS_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass

    # Check if elements already exist
    if web_url in data and "pages" in data[web_url] and page_url in data[web_url]["pages"]:
        return jsonify({
            "message": "Elements already exist",
            "elements": data[web_url]["pages"][page_url]
        })

    # Agar exist nahi karte to scrape karo
    try:
        res = requests.get(page_url, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        elements = []

        target_tags = ["a", "button", "form", "input", "img", "video"]

        for tag in soup.find_all(target_tags):
            selector = get_selector(tag)
            if not selector:
                continue

            name = (
                tag.get("aria-label") or
                tag.get("alt") or
                tag.get("placeholder") or
                tag.get("title") or
                tag.get("name") or
                tag.get("value") or
                tag.get("href") or
                tag.get("src") or
                tag.get("id") or
                " ".join(tag.get("class", [])) or
                tag.name
            )

            elements.append({
                "name": str(name).strip()[:60],
                "selector": selector,
                "tag": tag.name,
                "id": tag.get("id", ""),
                "classes": " ".join(tag.get("class", [])),
                "text": tag.get_text(strip=True)
            })

        # Ensure web_url structure
        if web_url not in data:
            data[web_url] = {"pages": {}}

        # Save elements under page_url
        data[web_url]["pages"][page_url] = elements

        # Write back to static file
        with open(ELEMENTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        return jsonify({"message": "Elements saved", "elements": elements})

    except Exception as e:
        print("Error fetching elements:", e)
        return jsonify({"error": str(e)}), 500


def get_selector(tag):
    """Generate CSS selector for element"""
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
    


RULES_FILE = os.path.join(app.root_path, "static", "rules.json")

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

    # Load existing rules from static
    rules = []
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r") as f:
            try:
                rules = json.load(f)
            except json.JSONDecodeError:
                pass

    rules.append(rule)

    # Save back to static file
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2)

    return jsonify({"message": "Rule added", "rule": rule})
@app.route("/get_rules")
def get_rules():
    try:
        rules_path = os.path.join(app.root_path, "static", "rules.json")
        with open(rules_path, "r") as f:
            rules = json.load(f)
    except Exception as e:
        print("Error reading rules:", e)
        rules = []
    return jsonify(rules)


# @app.route("/get_rules")
# def get_rules():
#     try:
#         with open("rules.json", "r") as f:
#             rules = json.load(f)
#     except:
#         rules = []
#     return jsonify(rules)

import os

@app.route("/track_event", methods=["POST"])
def track_event():
    try:
        data = request.get_json()
        events_file_path = os.path.join(app.root_path, "static", "events.json")

        # If file doesn't exist, create an empty list
        if not os.path.exists(events_file_path):
            events = []
        else:
            with open(events_file_path, "r") as f:
                try:
                    events = json.load(f)
                except json.JSONDecodeError:
                    events = []

        events.append(data)

        with open(events_file_path, "w") as f:
            json.dump(events, f, indent=2)

        return jsonify({"message": "Event tracked successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# @app.route("/track_event", methods=["POST"])
# def track_event():
#     try:
#         data = request.get_json()
#         with open("events.json", "r") as f:
#             try:
#                 events = json.load(f)
#             except:
#                 events = []

#         events.append(data)
#         with open("events.json", "w") as f:
#             json.dump(events, f, indent=2)

#         return jsonify({"message": "Event tracked successfully"}), 200
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

# @app.route("/get_events")
# def get_events():
#     try:
#         with open("events.json", "r") as f:
#             try:
#                 events = json.load(f)
#             except json.JSONDecodeError:
#                 events = []
#     except FileNotFoundError:
#         events = []
#     return jsonify(events)

@app.route("/get_events")
def get_events():
    try:
        events_path = os.path.join(app.root_path, "static", "events.json")

        if not os.path.exists(events_path):
            return jsonify([])

        with open(events_path, "r") as f:
            try:
                events = json.load(f)
            except json.JSONDecodeError:
                events = []
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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


# @app.route("/setup", methods=["POST"])
# def setup():
#     data = request.get_json()
#     site_url = data.get("webflow_url")

#     # Extract pages from site
#     try:
#         res = requests.get(site_url, timeout=10)
#         soup = BeautifulSoup(res.text, "html.parser")

#         from urllib.parse import urljoin

#         pages = []
#         for tag in soup.find_all("a", href=True):
#             href = tag['href']
#             if href.startswith("#") or "mailto:" in href or (href.startswith("http") and site_url not in href):
#                 continue
#             full_url = urljoin(site_url, href)
#             label = tag.get_text(strip=True) or full_url
#             pages.append({
#                 "label": label[:40],
#                 "url": full_url
#             })

#         site_data = {
#             "webflow_url": site_url,
#             "pages": pages
#         }

#         with open("site_config.json", "w") as f:
#             json.dump(site_data, f, indent=2)

#         return jsonify({"message": "Setup saved", "pages": pages})
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

@app.route("/setup", methods=["POST"])
def setup():
    import os
    import json
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    data = request.get_json()
    site_url = data.get("webflow_url")
    if not site_url:
        return jsonify({"error": "Missing webflow_url"}), 400

    config_path = os.path.join(app.static_folder, "site_config.json")

    # Load existing sites as a list
    all_sites = []
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                all_sites = json.load(f)
            except json.JSONDecodeError:
                all_sites = []

    # Check if site already exists
    for site in all_sites:
        if site.get("webflow_url") == site_url:
            return jsonify({
                "message": "Website already exists",
                "pages": site.get("pages", [])
            })

    # Scrape pages if not exist
    try:
        res = requests.get(site_url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

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

        # Add new site to the list
        new_site = {
            "webflow_url": site_url,
            "pages": pages
        }
        all_sites.append(new_site)

        # Save back to static/site_config.json
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(all_sites, f, indent=2)

        return jsonify({"message": "Setup saved", "pages": pages})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/get_config")
def get_config():
    try:
        path = os.path.join(app.static_folder, "site_config.json")
        with open(path, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "path": path})

@app.route("/delete_site_config", methods=["DELETE"])
def delete_site_config():
    if os.path.exists("site_config.json"):
        os.remove("site_config.json")
        return jsonify({"message": "Site config deleted"})
    return jsonify({"message": "No config found"}), 404


# @app.route("/extract_pages")
# def extract_pages():
#     site_url = request.args.get("site_url")

#     if not site_url:
#         return jsonify({"error": "Missing site_url"}), 400

#     try:
#         res = requests.get(site_url, timeout=10)
#         soup = BeautifulSoup(res.text, "html.parser")

#         links_seen = set()
#         pages = []

#         for a in soup.find_all("a", href=True):
#             href = a["href"].strip()

#             # Skip invalid/irrelevant links
#             if (
#                 href.startswith("#") or
#                 "mailto:" in href or
#                 "tel:" in href or
#                 href.startswith("javascript:")
#             ):
#                 continue

#             full_url = urljoin(site_url, href)
#             parsed = urlparse(full_url)

#             # Only include links from same domain
#             if parsed.netloc != urlparse(site_url).netloc:
#                 continue

#             if full_url in links_seen:
#                 continue
#             links_seen.add(full_url)

#             # Set label based on path only
#             path = parsed.path.rstrip("/")
#             label = "index" if path == "" or path == "/" else path.split("/")[-1]

#             pages.append({
#                 "label": label,
#                 "url": full_url
#             })
#         print(pages)
#         return jsonify(pages)

#     except Exception as e:
#         return jsonify({"error": str(e)}), 500

@app.route("/extract_pages")
def extract_pages():
    site_url = request.args.get("site_url")
    if not site_url:
        return jsonify({"error": "Missing site_url"}), 400

    import os
    config_path = os.path.join(app.static_folder, "site_config.json")

    if not os.path.exists(config_path):
        return jsonify({"error": "site_config.json not found"}), 404

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            all_sites = json.load(f)

        # all_sites is now a list of dicts
        matched_site = next((site for site in all_sites if site.get("webflow_url") == site_url), None)
        if not matched_site:
            return jsonify({"error": "Website not found in site_config.json"}), 404

        pages = matched_site.get("pages", [])
        return jsonify(pages)

    except json.JSONDecodeError:
        return jsonify({"error": "Corrupted site_config.json"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
