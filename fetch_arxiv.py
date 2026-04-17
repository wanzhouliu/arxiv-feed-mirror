#!/usr/bin/env python3
"""
Fetch today's cs.CV announcements from arXiv.
Output: JSON with full metadata for each paper.
"""
import json
import sys
import time
import re
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

RSS_URL = "https://rss.arxiv.org/atom/cs.CV"
API_URL = "http://export.arxiv.org/api/query"
BATCH_SIZE = 100

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "arxiv-feed-mirror/1.0"})
    with urlopen(req, timeout=30) as r:
        return r.read()


def parse_rss(xml_bytes: bytes):
    """Return list of (arxiv_id, announce_type) from the RSS/Atom feed."""
    root = ET.fromstring(xml_bytes)
    entries = []
    for entry in root.findall("atom:entry", NS):
        # entry id looks like "oai:arXiv.org:2501.12345v2"
        raw_id = entry.find("atom:id", NS).text
        m = re.search(r"(\d{4}\.\d{4,5})", raw_id)
        if not m:
            continue
        arxiv_id = m.group(1)
        announce_type_el = entry.find("arxiv:announce_type", NS)
        announce_type = announce_type_el.text if announce_type_el is not None else "unknown"
        entries.append({"arxiv_id": arxiv_id, "announce_type": announce_type})
    return entries


def parse_api_response(xml_bytes: bytes):
    """Return list of full-metadata dicts."""
    root = ET.fromstring(xml_bytes)
    papers = []
    for entry in root.findall("atom:entry", NS):
        arxiv_id_raw = entry.find("atom:id", NS).text
        m = re.search(r"(\d{4}\.\d{4,5})", arxiv_id_raw)
        if not m:
            continue
        arxiv_id = m.group(1)
        title = entry.find("atom:title", NS).text.strip()
        summary = entry.find("atom:summary", NS).text.strip()
        authors = [
            a.find("atom:name", NS).text
            for a in entry.findall("atom:author", NS)
        ]
        comment_el = entry.find("arxiv:comment", NS)
        comment = comment_el.text if comment_el is not None else None
        primary_cat_el = entry.find("arxiv:primary_category", NS)
        primary_cat = primary_cat_el.get("term") if primary_cat_el is not None else None
        cats = [c.get("term") for c in entry.findall("atom:category", NS)]
        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": summary,
            "authors": authors,
            "comment": comment,
            "primary_category": primary_cat,
            "categories": cats,
        })
    return papers


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- RSS ---
    rss_raw = fetch(RSS_URL)
    announcements = parse_rss(rss_raw)

    if not announcements:
        out = {
            "date": today,
            "status": "empty_feed",
            "count": 0,
            "papers": [],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # --- API (batch by 100) ---
    id_to_type = {a["arxiv_id"]: a["announce_type"] for a in announcements}
    all_ids = list(id_to_type.keys())
    enriched = []
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch = all_ids[i:i + BATCH_SIZE]
        qs = urlencode({
            "id_list": ",".join(batch),
            "max_results": BATCH_SIZE,
        })
        api_raw = fetch(f"{API_URL}?{qs}")
        enriched.extend(parse_api_response(api_raw))
        time.sleep(3)  # be polite: arXiv asks for 3s between API calls

    # merge announce_type back in
    for paper in enriched:
        paper["announce_type"] = id_to_type.get(paper["arxiv_id"], "unknown")

    out = {
        "date": today,
        "status": "ok",
        "count": len(enriched),
        "papers": enriched,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
