"""Step 2: query sources using oblique angles → pool of Candidate objects.

Sources (all open/public, no API key required):
  poetrydb   - poetrydb.org (classic poems)
  wikipedia  - Wikipedia search + extract (concepts, facts)
  wiktionary - Wiktionary etymologies
  met        - Metropolitan Museum of Art (open-access images)
  aic        - Art Institute of Chicago (open-access images)
  cma        - Cleveland Museum of Art (open-access images)

Every source queries on the angle's short `term`, never its prose. These APIs
are keyword search engines: a sentence-length query returns nothing at all (or
matches on stopwords like "the"), which is what quietly starved the pool.

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
from .distill import Angle

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "daily-poem/1.0 (personal e-ink frame; contact via github.com/eugenelyle/daily-poem)"}
_TIMEOUT = 10
_WIKI_HITS_PER_TERM = 5  # >1 so a term family doesn't funnel to one article


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

def gather(angles: list[Angle], cfg: Config) -> list[Candidate]:
    """Fetch candidates from all enabled sources in parallel."""
    n = cfg.companion.candidates_per_source
    sources = cfg.companion.sources

    fetchers = {
        "poetrydb":   lambda: _fetch_poetrydb(angles, n),
        "wikipedia":  lambda: _fetch_wikipedia(angles, n),
        "wiktionary": lambda: _fetch_wiktionary(angles, n),
        "met":        lambda: _fetch_met(angles, n),
        "aic":        lambda: _fetch_aic(angles, n),
        "cma":        lambda: _fetch_cma(angles, n),
    }

    unknown = [s for s in sources if s not in fetchers]
    if unknown:
        log.warning("unknown source(s) in config, ignored: %s", ", ".join(unknown))

    candidates: list[Candidate] = []
    futures = {}
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        for name in sources:
            if name in fetchers:
                futures[pool.submit(fetchers[name])] = name

        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results = fut.result()
                candidates.extend(results)
                # INFO, not DEBUG: a source silently returning 0 is the failure
                # mode that hid for weeks. It should be visible in journalctl.
                log.info("source %-11s -> %d candidates", name, len(results))
            except Exception as exc:
                log.warning("source %-11s FAILED: %s", name, exc)

    return candidates


# ---------------------------------------------------------------------------
# Source: PoetryDB
# ---------------------------------------------------------------------------

def _fetch_poetrydb(angles: list[Angle], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        # Search by title keyword. (/lines/ would be a richer match but has been
        # returning 503 upstream; /title/ answers reliably for a short term.)
        url = f"https://poetrydb.org/title/{requests.utils.quote(angle.term)}"
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

def _fetch_wikipedia(angles: list[Angle], n: int) -> list[Candidate]:
    """Search each term and keep several hits, not just the top one.

    srlimit=1 made this a funnel: 'apophatic', 'via negativa' and 'negative
    theology' all resolve to the same single article, so any angle in that family
    produced the identical candidate. Taking the first few hits per term restores
    the spread (that same search also offers Agnosticism, Différance,
    Pseudo-Dionysius).
    """
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            search_resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": angle.term,
                        "srlimit": _WIKI_HITS_PER_TERM, "format": "json"},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            hits = search_resp.json().get("query", {}).get("search", [])
        except Exception:
            continue

        for hit in hits:
            if len(results) >= n:
                break
            title = hit.get("title", "")
            if not title or title in seen or _is_index_article(title):
                continue
            seen.add(title)
            try:
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
            except Exception:
                continue
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

    return results


def _is_index_article(title: str) -> bool:
    """Skip Wikipedia's list/index/glossary pages — they never deepen a poem.

    ('List of Latin phrases (full)' was a real companion candidate.)
    """
    low = title.lower()
    return (low.startswith(("list of", "index of", "glossary of", "outline of",
                            "timeline of", "comparison of"))
            or low.endswith(("(disambiguation)",)))


# ---------------------------------------------------------------------------
# Source: Wiktionary (etymology)
# ---------------------------------------------------------------------------

def _fetch_wiktionary(angles: list[Angle], n: int) -> list[Candidate]:
    """Pull the Etymology section for each term.

    This source returned nothing for its entire life: it asked for `exintro`,
    but a Wiktionary entry has no lead section before its first heading, so the
    extract came back empty for every word — including the design doc's own
    examples (want, nostalgia). Fetch the whole page and cut the Etymology
    section out ourselves.
    """
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        word = angle.term.strip().lower()
        if not word or word in seen:
            continue
        seen.add(word)
        try:
            resp = requests.get(
                "https://en.wiktionary.org/w/api.php",
                params={"action": "query", "prop": "extracts", "titles": word,
                        "format": "json", "explaintext": True},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            pages = resp.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()))
            if page.get("missing") is not None:
                continue
            etymology = extract_etymology(page.get("extract") or "")
        except Exception:
            continue
        if not etymology:
            continue

        results.append(Candidate(
            id=_make_id("wiktionary", word),
            type="text",
            content_or_description=f"Etymology of '{word}':\n\n{etymology}",
            source_name="Wiktionary",
            attribution=f"Wiktionary: {word}",
            url=f"https://en.wiktionary.org/wiki/{requests.utils.quote(word)}",
        ))

    return results


def extract_etymology(extract: str, max_chars: int = 600) -> str:
    """Cut the first Etymology section out of a plaintext Wiktionary extract.

    Sections arrive as '=== Etymology ===' (or 'Etymology 1' where a word has
    several). Returns "" when the entry has no etymology at all.
    """
    lines = extract.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().strip("= ").lower().startswith("etymology"):
            start = i + 1
            break
    if start is None:
        return ""

    body: list[str] = []
    for line in lines[start:]:
        if line.strip().startswith("="):  # next heading ends the section
            break
        if line.strip():
            body.append(line.strip())
    text = " ".join(body).strip()
    return text[:max_chars] if len(text) >= 20 else ""


# ---------------------------------------------------------------------------
# Source: Metropolitan Museum of Art
# ---------------------------------------------------------------------------

def _fetch_met(angles: list[Angle], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            search_resp = requests.get(
                "https://collectionapi.metmuseum.org/public/collection/v1/search",
                params={"q": angle.term, "hasImages": "true"},
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

def _fetch_aic(angles: list[Angle], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            resp = requests.get(
                "https://api.artic.edu/api/v1/artworks/search",
                params={
                    "q": angle.term,
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
# Source: Cleveland Museum of Art
# ---------------------------------------------------------------------------
# Replaces the Rijksmuseum fetcher, which had gone dead: their data.rijksmuseum.nl
# endpoint is now a bare Linked-Art enumeration that rejects `q` outright
# ("Unsupported query parameter") and carries no titles or images in the listing.
# Cleveland is open, keyless, keyword-searchable, and was already named as a
# source in the design doc.

def _fetch_cma(angles: list[Angle], n: int) -> list[Candidate]:
    seen: set[str] = set()
    results: list[Candidate] = []

    for angle in angles:
        if len(results) >= n:
            break
        try:
            resp = requests.get(
                "https://openaccess-api.clevelandart.org/api/artworks/",
                params={"q": angle.term, "has_image": 1, "cc0": 1, "limit": 6},
                headers=_HEADERS, timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            items = resp.json().get("data", [])
        except Exception:
            continue

        for item in items:
            if len(results) >= n:
                break
            obj_id = item.get("id")
            if not obj_id or f"cma:{obj_id}" in seen:
                continue
            seen.add(f"cma:{obj_id}")

            image_url = ((item.get("images") or {}).get("web") or {}).get("url", "")
            if not image_url:
                continue

            title = item.get("title") or "Untitled"
            creators = item.get("creators") or []
            artist = (creators[0].get("description", "") if creators else "").strip()
            date = item.get("creation_date") or ""
            medium = item.get("technique") or ""
            description = f"{title}{' — ' + artist if artist else ''}{', ' + date if date else ''}"
            if medium:
                description += f"\nMedium: {medium}"

            results.append(Candidate(
                id=_make_id("cma", str(obj_id)),
                type="image",
                content_or_description=description,
                source_name="Cleveland Museum of Art",
                attribution=f"{title}{', ' + artist if artist else ''}. Cleveland Museum of Art.",
                url=item.get("url") or f"https://clevelandart.org/art/{obj_id}",
                image_url=image_url,
            ))

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id(*parts: str) -> str:
    return hashlib.md5(":".join(parts).encode()).hexdigest()[:12]
