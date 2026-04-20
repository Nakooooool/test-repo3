# ─────────────────────────────────────────
#  Glimpse-web  |  Flask Backend  |  app.py
# ─────────────────────────────────────────
import os, json, uuid
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

NEWS_API_KEY   = os.getenv("NEWS_API_KEY", "YOUR_API_KEY_HERE")
NEWS_API_BASE  = "https://newsapi.org/v2"
BOOKMARKS_FILE = "bookmarks.json"

# Map frontend tab slugs → NewsAPI category values
CATEGORY_MAP = {
    "tech":          "technology",
    "sports":        "sports",
    "business":      "business",
    "health":        "health",
    "entertainment": "entertainment",
    "general":       "general",
}

# ── Indian Express RSS ───────────────────────
# Fetches news directly from Indian Express RSS feeds (no API key required).
# Each category maps to the official Indian Express section feed.
import xml.etree.ElementTree as ET
import re as _re

INDIAN_EXPRESS_RSS = {
    "general":       "https://indianexpress.com/feed/",
    "tech":          "https://indianexpress.com/section/technology/feed/",
    "sports":        "https://indianexpress.com/section/sports/feed/",
    "business":      "https://indianexpress.com/section/business/feed/",
    "health":        "https://indianexpress.com/section/lifestyle/health/feed/",
    "entertainment": "https://indianexpress.com/section/entertainment/feed/",
}

def _extract_ie_image(item):
    """Try to pull the featured image URL out of an Indian Express RSS item."""
    # 1. <media:content url="...">
    for child in item:
        if child.tag.endswith("}content") and child.get("url"):
            return child.get("url")
        if child.tag.endswith("}thumbnail") and child.get("url"):
            return child.get("url")
    # 2. <enclosure url="..." type="image/...">
    enc = item.find("enclosure")
    if enc is not None and (enc.get("type", "").startswith("image") or enc.get("url", "")):
        return enc.get("url", "")
    # 3. First <img src="..."> inside description HTML
    desc = item.findtext("description") or ""
    m = _re.search(r'<img[^>]+src=["']([^"']+)["']', desc)
    if m:
        return m.group(1)
    return ""

def fetch_indian_express(category="general", max_items=12):
    """
    Fetch and parse Indian Express RSS for the given category.
    Returns a list of article dicts in the same shape as fmt().
    Falls back to an empty list on any error.
    """
    url = INDIAN_EXPRESS_RSS.get(category, INDIAN_EXPRESS_RSS["general"])
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:max_items]
        articles = []
        for item in items:
            title  = (item.findtext("title") or "").strip()
            link   = (item.findtext("link")  or "#").strip()
            desc   = item.findtext("description") or ""
            # Strip HTML tags from description
            clean_desc = _re.sub(r"<[^>]+>", "", desc).strip()
            pub    = (item.findtext("pubDate") or "").strip()
            author = (item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip()
            image  = _extract_ie_image(item)
            if not title:
                continue
            articles.append({
                "id":          link,
                "title":       title,
                "description": clean_desc,
                "content":     clean_desc,
                "url":         link,
                "image":       image,
                "source":      "Indian Express",
                "publishedAt": pub,
                "author":      author,
            })
        return articles
    except Exception:
        return []

# GET /api/indian-express?category=tech
@app.route("/api/indian-express")
def get_indian_express():
    """Return news fetched directly from Indian Express RSS feeds."""
    category = request.args.get("category", "general").lower()
    articles = fetch_indian_express(category)
    return jsonify({"articles": articles, "totalResults": len(articles)})

# ── Bookmark file helpers ─────────────────
def load_bookmarks():
    if not os.path.exists(BOOKMARKS_FILE):
        return []
    with open(BOOKMARKS_FILE, "r") as f:
        try:    return json.load(f)
        except: return []

def save_bookmarks(data):
    with open(BOOKMARKS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── Normalise article shape ───────────────
def fmt(article, idx=0):
    return {
        "id":          article.get("url", str(idx)),
        "title":       article.get("title", "No title"),
        "description": article.get("description", ""),
        "content":     article.get("content", ""),
        "url":         article.get("url", "#"),
        "image":       article.get("urlToImage", ""),
        "source":      article.get("source", {}).get("name", "Unknown"),
        "publishedAt": article.get("publishedAt", ""),
        "author":      article.get("author", ""),
    }

# ── Routes ───────────────────────────────

@app.route("/")
def index():
    """Serve the Glimpse-web single-page app."""
    return render_template("index.html")

# GET /api/news?category=tech&page=1
@app.route("/api/news")
def get_news():
    category = request.args.get("category", "general").lower()
    page     = request.args.get("page", 1, type=int)
    api_cat  = CATEGORY_MAP.get(category, "general")

    # Try NewsAPI first if a real key is configured
    newsapi_ok = NEWS_API_KEY not in ("YOUR_API_KEY_HERE", "paste_your_newsapi_key_here", "")
    if newsapi_ok:
        try:
            resp = requests.get(
                f"{NEWS_API_BASE}/top-headlines",
                params={"apiKey": NEWS_API_KEY, "category": api_cat,
                        "language": "en", "pageSize": 12, "page": page},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                articles = [fmt(a, i) for i, a in enumerate(data.get("articles", []))
                            if a.get("title") and a["title"] != "[Removed]"]
                if articles:
                    return jsonify({"articles": articles, "totalResults": data.get("totalResults", 0)})
        except Exception:
            pass  # fall through to Google News RSS

    # Fallback: Google News RSS (no API key needed, always works)
    articles = fetch_indian_express(category)
    return jsonify({"articles": articles, "totalResults": len(articles)})

# GET /api/search?q=keyword
@app.route("/api/search")
def search_news():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"articles": [], "totalResults": 0})

    # Try NewsAPI first if a real key is configured
    newsapi_ok = NEWS_API_KEY not in ("YOUR_API_KEY_HERE", "paste_your_newsapi_key_here", "")
    if newsapi_ok:
        try:
            resp = requests.get(
                f"{NEWS_API_BASE}/everything",
                params={"apiKey": NEWS_API_KEY, "q": q, "language": "en",
                        "sortBy": "publishedAt", "pageSize": 12},
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                articles = [fmt(a, i) for i, a in enumerate(data.get("articles", []))
                            if a.get("title") and a["title"] != "[Removed]"]
                if articles:
                    return jsonify({"articles": articles, "totalResults": data.get("totalResults", 0)})
        except Exception:
            pass  # fall through to Google News RSS

    # Fallback: search Indian Express RSS using their search feed
    try:
        rss_url = f"https://indianexpress.com/?s={requests.utils.quote(q)}&feed=rss2"
        resp = requests.get(rss_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")[:12]
        articles = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "#").strip()
            desc  = item.findtext("description") or ""
            clean_desc = _re.sub(r"<[^>]+>", "", desc).strip()
            pub   = (item.findtext("pubDate") or "").strip()
            author = (item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip()
            image = _extract_ie_image(item)
            if not title:
                continue
            articles.append({"id": link, "title": title, "description": clean_desc,
                              "content": clean_desc, "url": link, "image": image,
                              "source": "Indian Express", "publishedAt": pub, "author": author})
        return jsonify({"articles": articles, "totalResults": len(articles)})
    except Exception as e:
        return jsonify({"error": str(e), "articles": []}), 500

# GET /api/bookmarks
@app.route("/api/bookmarks", methods=["GET"])
def get_bookmarks():
    return jsonify({"articles": load_bookmarks()})

# POST /api/bookmarks  — body: article JSON
@app.route("/api/bookmarks", methods=["POST"])
def add_bookmark():
    article = request.get_json()
    if not article:
        return jsonify({"error": "No data provided"}), 400
    bookmarks = load_bookmarks()
    if article.get("id") in {b.get("id") for b in bookmarks}:
        return jsonify({"message": "Already saved", "articles": bookmarks})
    article.setdefault("bookmark_id", str(uuid.uuid4()))
    bookmarks.append(article)
    save_bookmarks(bookmarks)
    return jsonify({"message": "Saved to Glimpse!", "articles": bookmarks})

# DELETE /api/bookmarks/<article_id>
@app.route("/api/bookmarks/<path:article_id>", methods=["DELETE"])
def remove_bookmark(article_id):
    bookmarks = load_bookmarks()
    updated = [b for b in bookmarks if b.get("id") != article_id]
    save_bookmarks(updated)
    return jsonify({"message": "Removed from Glimpse", "articles": updated})

# ── Entry point ───────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, port=port, host="0.0.0.0")
