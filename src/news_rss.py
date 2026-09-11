
# AINEWS free RSS fetch (no paid API)
import requests, xml.etree.ElementTree as ET, json, os

FEEDS = {
    "BBC": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "Reuters": "https://www.reutersagency.com/feed/?query=breaking+news&format=xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "GoogleNews": "https://news.google.com/rss/search?q=breaking+news&hl=en-US&gl=US&ceid=US:en"
}

def fetch_headlines(query="breaking news", max_items=5):
    """Fetch from first available feed; return list of {title, url, summary}"""
    results = []
    for name, url in FEEDS.items():
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                # Simple XML parse — get item titles and links
                for item in root.iter("item"):
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    desc = item.findtext("description", "")[:200]
                    if title and len(title) > 3:
                        results.append({"title": title, "url": link, "summary": desc, "source": name})
                    if len(results) >= max_items:
                        break
            if results:
                break  # got some from first working feed
        except Exception as e:
            # Skip failed feeds — graceful
            continue
    return results[:max_items]

if __name__ == "__main__":
    items = fetch_headlines()
    print(f"Fetched {len(items)} news headlines")
    for it in items:
        print(f"  {it['source']}: {it['title']}")
