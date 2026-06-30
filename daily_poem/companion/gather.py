"""Step 2: query sources using oblique angles → pool of Candidate objects.

Sources (all open/public, no API key required):
  poetrydb   - poetrydb.org (classic poems)
  wikipedia  - Wikipedia search + extract (concepts, facts)
  wiktionary - Wiktionary etymologies
  met        - Metropolitan Museum of Art (open-access images)
  aic        - Art Institute of Chicago (open-access images)
  rijksmuseum - Rijksmuseum collection (open-access images)

Each source returns at most candidates_per_source results. Sources run in
parallel via ThreadPoolExecutor. Individual source failures are swallowed so
a down API doesn't abort the whole pipeline.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import requests

from ..config import Config

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "daily-poem/1.0 (personal e-ink frame; contact via github.com/eugenelyle/daily-poem)"}
_TIMEOUT = 10


@dataclass
class Candidate:
    id: str
    type: str                   # "text" | "image"
    content_or_description: str  # text content OR artwork title+description for ranking
    source_name: str
    attribution: str            # human-readable credit line
    url: str                    # source page URL
    image_url: str = ""         # direct image URL (images only)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def gather(angles: list[str], cfg: Config) -> list[Candidate]:
    """Fetch candidates from all enabled sources in parallel."""
    n = cfg.companion.candidates_per_source
    sources = cfg.companion.sources

    fetchers = {
        "poetrydb":    lambda: _fetch_poetrydb(angles, n),
        "wikipedia":   lambda: _fetch_wikipedia(angles, n),
        "wiktionary":  lambda: _fetch_wiktionary(angles, n),
        "met":         lambda: _fetch_met(angles, n),
        "aic":         lambda: _fetch_aic(angles, n),
        "rijksmuseum": lambda: _fetch_rijksmuseum(angles, n),
    }

    candidates: list[Candidate] = []
    futures = {}
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        for name in sources:
            if name in fetchers:
                futures[pool.submit(fetchers[name])] = name

        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results = fut.result()
                candidates.extend(results)
                log.debug("%s: %d candidates", name, len(results))
            except Exception as exc:
                log.warning("%s fetch failed: %s", name, exc)

    return candidates


# ---------------------------------------------------------------------------
# Source: PoetryDB
# ---------------------------------------------------------------------------

def _fetch_poetrydb(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        # Search by title keyword (more reliable than line search for oblique terms)
        url = f"https://poetrydb.org/title/{requests.utils.quote(angle)}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if isinstance(data, dict) and data.get("status") == 404:
                continue
            if not isinstance(data, list):
                continue
            for poem in data[:n]:
                title = poem.get("title", "")
                author = poem.get("author", "")
                lines = poem.get("lines", [])
                key = f"poetrydb:{title}:{author}"
                if key in seen or not lines:
                    continue
                seen.add(key)
                text = "\n".join(lines[:20])  # first 20 lines max
                results.append(Candidate(
                    id=_make_id("poetrydb", title, author),
                    type="text",
                    content_or_description=f"{title}\n{author}\n\n{text}",
                    source_name="PoetryDB",
                    attribution=f"{title} — {author}",
                    url=f"https://poetrydb.org/title/{requests.utils.quote(title)}",
                ))
                if len(results) >= n:
                    break
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Source: Wikipedia
# ---------------------------------------------------------------------------

def _fetch_wikipedia(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            # Search for the article
            search_resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": angle,
                        "srlimit": 1, "format": "json"},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            hits = search_resp.json().get("query", {}).get("search", [])
            if not hits:
                continue
            title = hits[0]["title"]
            if title in seen:
                continue
            seen.add(title)

            # Get the intro extract
            extract_resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "prop": "extracts", "exintro": True,
                        "exsentences": 4, "titles": title, "format": "json",
                        "explaintext": True},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            pages = extract_resp.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()))
            extract = (page.get("extract") or "").strip()
            if not extract:
                continue

            results.append(Candidate(
                id=_make_id("wikipedia", title),
                type="text",
                content_or_description=f"{title}\n\n{extract}",
                source_name="Wikipedia",
                attribution=f"Wikipedia: {title}",
                url=f"https://en.wikipedia.org/wiki/{requests.utils.quote(title.replace(' ', '_'))}",
            ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Source: Wiktionary (etymology)
# ---------------------------------------------------------------------------

def _fetch_wiktionary(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        # Use single-word angles for etymology (skip multi-word phrases)
        word = angle.strip().split()[0].lower()
        if word in seen:
            continue
        seen.add(word)
        try:
            resp = requests.get(
                "https://en.wiktionary.org/w/api.php",
                params={"action": "query", "prop": "extracts", "exintro": True,
                        "titles": word, "format": "json", "explaintext": True},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            pages = resp.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()))
            if page.get("missing") is not None:
                continue
            extract = (page.get("extract") or "").strip()
            if not extract or len(extract) < 30:
                continue
            # Take only the first meaningful chunk (etymology is near the top)
            extract = extract[:600]
            results.append(Candidate(
                id=_make_id("wiktionary", word),
                type="text",
                content_or_description=f"Etymology of '{word}':\n\n{extract}",
                source_name="Wiktionary",
                attribution=f"Wiktionary: {word}",
                url=f"https://en.wiktionary.org/wiki/{requests.utils.quote(word)}",
            ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Source: Metropolitan Museum of Art
# ---------------------------------------------------------------------------

def _fetch_met(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            search_resp = requests.get(
                "https://collectionapi.metmuseum.org/public/collection/v1/search",
                params={"q": angle, "hasImages": "true"},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            object_ids = search_resp.json().get("objectIDs") or []
            for obj_id in object_ids[:6]:  # try a few in case some lack images
                if len(results) >= n:
                    break
                key = f"met:{obj_id}"
                if key in seen:
                    continue
                seen.add(key)

                obj_resp = requests.get(
                    f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{obj_id}",
                    headers=_HEADERS, timeout=_TIMEOUT,
                )
                obj = obj_resp.json()
                image_url = obj.get("primaryImageSmall") or obj.get("primaryImage", "")
                if not image_url:
                    continue

                title = obj.get("title", "Untitled")
                artist = (obj.get("artistDisplayName") or "").strip()
                date = obj.get("objectDate", "")
                medium = obj.get("medium", "")
                base = f"{title}{' — ' + artist if artist else ''}{', ' + date if date else ''}"
                description = f"{base}\nMedium: {medium}" if medium else base

                results.append(Candidate(
                    id=_make_id("met", str(obj_id)),
                    type="image",
                    content_or_description=description,
                    source_name="Metropolitan Museum of Art",
                    attribution=f"{title}{', ' + artist if artist else ''}. The Metropolitan Museum of Art.",
                    url=obj.get("objectURL", f"https://www.metmuseum.org/art/collection/search/{obj_id}"),
                    image_url=image_url,
                ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Source: Art Institute of Chicago
# ---------------------------------------------------------------------------

def _fetch_aic(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            resp = requests.get(
                "https://api.artic.edu/api/v1/artworks/search",
                params={
                    "q": angle,
                    "fields": "id,title,image_id,artist_display,date_display,medium_display,thumbnail",
                    "limit": 6,
                },
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            for artwork in resp.json().get("data", []):
                if len(results) >= n:
                    break
                image_id = artwork.get("image_id")
                if not image_id:
                    continue
                key = f"aic:{artwork['id']}"
                if key in seen:
                    continue
                seen.add(key)

                title = artwork.get("title", "Untitled")
                artist = (artwork.get("artist_display") or "").strip()
                date = artwork.get("date_display", "")
                medium = artwork.get("medium_display", "")
                thumb = artwork.get("thumbnail") or {}
                alt_text = thumb.get("alt_text", "")
                description = f"{title}{' — ' + artist if artist else ''}{', ' + date if date else ''}"
                if alt_text:
                    description += f"\n{alt_text}"

                image_url = f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg"
                results.append(Candidate(
                    id=_make_id("aic", str(artwork["id"])),
                    type="image",
                    content_or_description=description,
                    source_name="Art Institute of Chicago",
                    attribution=f"{title}{', ' + artist if artist else ''}. Art Institute of Chicago.",
                    url=f"https://www.artic.edu/artworks/{artwork['id']}",
                    image_url=image_url,
                ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Source: Rijksmuseum
# ---------------------------------------------------------------------------

def _fetch_rijksmuseum(angles: list[str], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            resp = requests.get(
                "https://data.rijksmuseum.nl/search/collection",
                params={"q": angle, "type": "painting", "limit": 6},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            items = resp.json()
            # Handle both list and {"hits": [...]} response shapes
            if isinstance(items, dict):
                items = items.get("hits", items.get("artObjects", []))
            if not isinstance(items, list):
                continue

            for item in items:
                if len(results) >= n:
                    break
                # Normalize across potential response shapes
                obj_id = (item.get("id") or item.get("objectNumber") or
                          item.get("_id") or "")
                if not obj_id:
                    continue
                key = f"rijksmuseum:{obj_id}"
                if key in seen:
                    continue
                seen.add(key)

                src = item.get("_source", item)
                title = src.get("title", "") or item.get("title", "Untitled")
                maker = (src.get("principalMaker") or src.get("principalOrFirstMaker")
                         or item.get("principalOrFirstMaker") or "").strip()
                dating = src.get("dating", {})
                date = dating.get("presentingDate", "") if isinstance(dating, dict) else ""

                # Image URL — try several known shapes
                web_image = src.get("webImage") or item.get("webImage") or {}
                image_url = (web_image.get("url", "") or
                             src.get("headerImage", {}).get("url", "") or "")
                if not image_url:
                    continue

                description = f"{title}{' — ' + maker if maker else ''}{', ' + date if date else ''}"
                results.append(Candidate(
                    id=_make_id("rijksmuseum", str(obj_id)),
                    type="image",
                    content_or_description=description,
                    source_name="Rijksmuseum",
                    attribution=f"{title}{', ' + maker if maker else ''}. Rijksmuseum, Amsterdam.",
                    url=f"https://www.rijksmuseum.nl/en/collection/{obj_id}",
                    image_url=image_url,
                ))
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id(*parts: str) -> str:
    return hashlib.md5(":".join(parts).encode()).hexdigest()[:12]
