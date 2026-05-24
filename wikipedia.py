"""MediaWiki-backed lookup with on-disk caching.

Public surface: `search_wikipedia(query: str) -> list[dict]`.

The query string is overloaded to support two modes:
  - "article: <exact title>"  -> fetch the full plain-text article for that title
  - anything else             -> MediaWiki search; returns top hits with intros
"""

import hashlib
import json
from pathlib import Path

import requests

API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "wikipedia_eval/0.1 (Anthropic prompt-eng take-home)"
TOP_N = 5
TIMEOUT_SECONDS = 30
CACHE_DIR = Path(__file__).parent / "cache" / "wikipedia"
ARTICLE_PREFIX = "article:"


def _hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _read_cache(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_cache(path: Path, results: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _do_search(query: str) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "inprop": "url",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": TOP_N,
        "exintro": "true",
        "explaintext": "true",
    }
    resp = requests.get(
        API_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    ordered = sorted(pages.values(), key=lambda p: p.get("index", 10**9))
    return [
        {
            "title": p.get("title", ""),
            "url": p.get("fullurl", ""),
            "extract": (p.get("extract") or "").strip(),
        }
        for p in ordered
    ]


def _do_fetch_article(title: str) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "inprop": "url",
        "titles": title,
        "explaintext": "true",
        "redirects": "1",
    }
    resp = requests.get(
        API_URL,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    results = []
    for p in pages.values():
        if "missing" in p:
            continue
        results.append(
            {
                "title": p.get("title", ""),
                "url": p.get("fullurl", ""),
                "extract": (p.get("extract") or "").strip(),
            }
        )
    return results


def search_wikipedia(query: str) -> list[dict]:
    """Look things up on English Wikipedia.

    - "article: <title>"  -> single full-text article (or empty list if missing)
    - anything else       -> top {TOP_N} search hits with intro extracts
    Returns [{title, url, extract}, ...].
    """
    stripped = query.strip()
    if stripped.lower().startswith(ARTICLE_PREFIX):
        title = stripped[len(ARTICLE_PREFIX) :].strip()
        cache_path = CACHE_DIR / "article" / f"{_hash(title)}.json"
        cached = _read_cache(cache_path)
        if cached is not None:
            return cached
        results = _do_fetch_article(title)
        _write_cache(cache_path, results)
        return results

    cache_path = CACHE_DIR / "search" / f"{_hash(stripped)}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached
    results = _do_search(stripped)
    _write_cache(cache_path, results)
    return results
