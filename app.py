# ─────────────────────────────────────────
#  Glimpse-web  |  Flask Backend  |  app.py
# ─────────────────────────────────────────
import os
import json
import uuid
import re
import xml.etree.ElementTree as ET

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

NEWS_API_KEY   = os.getenv("NEWS_API_KEY", "")
NEWS_API_BASE  = "https://newsapi.org/v2"
BOOKMARKS_FILE = os.getenv("BOOKMARKS_FILE", "bookmarks.json")

# Map frontend tab slugs → NewsAPI category values
CATEGORY_MAP = {
    "general":       "general",
    "tech":          "technology",
    "sports":        "sports",
    "business":      "business",
    "health":        "health",
    "entertainment": "entertainment",
}

# ── Indian Express RSS feeds per category ──────────────────────────────────────
INDIAN_EXPRESS_RSS = {
    "general":       "https://indianexpress.com/feed/",
    "tech":          "https://indianexpress.com/section/technology/feed/",
    "sports":        "https://indianexpress.com/section/sports/feed/",
    "business":      "https://indianexpress.com/section/business/feed/",
    "health":        "https://indianexpress.com/section/lifestyle/health/feed/",
    "entertainment": "https://indianexpress.com/section/entertainment/feed/",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Glimpse-web/1.0)"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _ie_image(item) -> str:
    """Extract featured image from an Indian Express RSS <item>."""
    for child in item:
        tag = child.tag.lower()
        if ("content" in tag or "thumbnail" in tag) and child.get("url"):
            return child.get("url")
    enc = item.find("enclosure")
    if enc is not None and enc.get("url"):
        return enc.get("url")
    desc = item.findtext("description") or ""
    # Match src="..." or src='...'
    dq = desc.find('src="')
    if dq != -1:
        end = desc.find('"', dq + 5)
        if end != -1:
            return desc[dq + 5:end]
    sq = desc.find("src='")
    if sq != -1:
        end = desc.find("'", sq + 5)
        if end != -1:
            return desc[sq + 5:end]
    return ""


def _parse_rss(xml_bytes: bytes, default_source: str = "Indian Express") -> list:
    """Parse RSS XML bytes → list of article dicts."""
    root = ET.fromstring(xml_bytes)
    articles = []
    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        if not title:
            continue
        link    = (item.findtext("link") or "#").strip()
        desc    = _strip_html(item.findtext("description") or "")
        pub     = (item.findtext("pubDate") or "").strip()
        author  = _strip_html(
            item.findtext("{http://purl.org/dc/elements/1.1/}creator") or ""
        )
        src_el  = item.find("source")
        source  = (src_el.text or default_source).strip() if src_el is not None else default_source
        image   = _ie_image(item)
        articles.append({
            "id":          link,
            "title":       title,
            "description": desc,
            "content":     desc,
            "url":         link,
            "image":       image,
            "source":      source,
            "publishedAt": pub,
            "author":      author,
        })
    return articles


def fetch_indian_express(category: str = "general", max_items: int = 20) -> list:
    url = INDIAN_EXPRESS_RSS.get(category, INDIAN_EXPRESS_RSS["general"])
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS)
        resp.raise_for_status()
        return _parse_rss(resp.content)[:max_items]
    except Exception:
        return []


def fetch_ie_search(query: str, max_items: int = 20) -> list:
    url = f"https://indianexpress.com/?s={requests.utils.quote(query)}&feed=rss2"
    try:
        resp = requests.get(url, timeout=12, headers=HEADERS)
        resp.raise_for_status()
        return _parse_rss(resp.content)[:max_items]
    except Exception:
        return []


def fmt(article: dict, idx: int = 0) -> dict:
    """Normalise a NewsAPI article to the common shape."""
    return {
        "id":          article.get("url", str(idx)),
        "title":       article.get("title", "No title"),
        "description": article.get("description") or "",
        "content":     article.get("content") or "",
        "url":         article.get("url", "#"),
        "image":       article.get("urlToImage") or "",
        "source":      article.get("source", {}).get("name", "Unknown"),
        "publishedAt": article.get("publishedAt") or "",
        "author":      article.get("author") or "",
    }


# ── Bookmark helpers ───────────────────────────────────────────────────────────

def load_bookmarks() -> list:
    if not os.path.exists(BOOKMARKS_FILE):
        return []
    try:
        with open(BOOKMARKS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_bookmarks(data: list) -> None:
    try:
        with open(BOOKMARKS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/news")
def get_news():
    category = request.args.get("category", "general").lower()
    page     = request.args.get("page", 1, type=int)

    # Try NewsAPI first if a valid key exists
    if NEWS_API_KEY and NEWS_API_KEY not in ("YOUR_API_KEY_HERE", "paste_your_newsapi_key_here"):
        try:
            resp = requests.get(
                f"{NEWS_API_BASE}/top-headlines",
                params={
                    "apiKey":   NEWS_API_KEY,
                    "category": CATEGORY_MAP.get(category, "general"),
                    "language": "en",
                    "pageSize": 20,
                    "page":     page,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                articles = [
                    fmt(a, i)
                    for i, a in enumerate(data.get("articles", []))
                    if a.get("title") and a["title"] != "[Removed]"
                ]
                if articles:
                    return jsonify({"articles": articles, "totalResults": data.get("totalResults", 0), "source": "newsapi"})
        except Exception:
            pass

    # Fallback: Indian Express RSS
    articles = fetch_indian_express(category)
    return jsonify({"articles": articles, "totalResults": len(articles), "source": "indianexpress"})


@app.route("/api/search")
def search_news():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"articles": [], "totalResults": 0})

    # Try NewsAPI first
    if NEWS_API_KEY and NEWS_API_KEY not in ("YOUR_API_KEY_HERE", "paste_your_newsapi_key_here"):
        try:
            resp = requests.get(
                f"{NEWS_API_BASE}/everything",
                params={
                    "apiKey":   NEWS_API_KEY,
                    "q":        q,
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "pageSize": 20,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                articles = [
                    fmt(a, i)
                    for i, a in enumerate(data.get("articles", []))
                    if a.get("title") and a["title"] != "[Removed]"
                ]
                if articles:
                    return jsonify({"articles": articles, "totalResults": data.get("totalResults", 0)})
        except Exception:
            pass

    # Fallback: Indian Express search
    articles = fetch_ie_search(q)
    return jsonify({"articles": articles, "totalResults": len(articles)})


@app.route("/api/bookmarks", methods=["GET"])
def get_bookmarks():
    return jsonify({"articles": load_bookmarks()})


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


@app.route("/api/bookmarks/<path:article_id>", methods=["DELETE"])
def remove_bookmark(article_id):
    bookmarks = load_bookmarks()
    updated = [b for b in bookmarks if b.get("id") != article_id]
    save_bookmarks(updated)
    return jsonify({"message": "Removed from Glimpse", "articles": updated})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, port=port, host="0.0.0.0")
