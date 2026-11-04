"""Discover public event pages and build an M3U of directly playable HLS streams.

Does not bypass authentication, DRM, geoblocks, paywalls, or token checks.
M3U entries are only emitted for verified HLS URLs (not event/player webpages).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
import json
import logging
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from .thumbnails import create_thumbnail

LOG = logging.getLogger("zerolive")
STREAM_RE = re.compile(r"(?:https?:)?//[^\s\"'<>\\]+?\.m3u8(?:\?[^\s\"'<>\\]*)?", re.I)
STREAM_MARKER = re.compile(r"(?:\.m3u8)(?:\?|$)", re.I)
EVENT_PATH = re.compile(r"(?:ppv-streams|/watch/|/live/|/event/|/stream/)", re.I)
REMOVE_BRAND = re.compile(r"\b(?:roxie[ -]?streams?)\b", re.I)
REMOVE_STREAM = re.compile(r"\s*(?:[-|:()]\s*)?(?:stream|mirror|server)\s*#?\d+\s*$", re.I)
SANE_LINK = re.compile(r"^[a-zA-Z][a-zA-Z0-9 +.&'()/-]{3,110}$")
UA = "ZeroLive/1.0 (+https://github.com/Zer0Spce/ZeroLive; public-metadata-collector)"


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    category: str
    logo: str
    source_page: str


def clean_name(value: str) -> str:
    """Produce readable event names without source-site advertising."""
    name = unescape(value or "")
    name = REMOVE_BRAND.sub("", name)
    name = REMOVE_STREAM.sub("", name)
    name = re.sub(r"\s*[-|:]\s*$", "", name)
    name = re.sub(r"\b(?:v|vs)\.?\s+", "vs. ", name, flags=re.I)
    name = re.sub(r"\s+", " ", name).strip(" -|:·")
    if name.isupper() and len(name) > 6:
        special = {"NBA", "NFL", "UFC", "NHL", "MLB", "WWE", "AEW", "NCAA", "F1", "PPV", "TV", "USA"}
        name = " ".join(w if w.strip(".:-") in special or (w.isupper() and len(w) <= 4) else w.capitalize() for w in name.split())
    return name or "Live Event"


def event_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", clean_name(value).lower())


def normalize_url(url: str, base: str = "") -> str:
    url = unescape((url or "").replace("\\/", "/")).strip().strip('"\'')
    if url.startswith("//"):
        url = "https:" + url
    if base:
        url = urljoin(base, url)
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        return ""
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return ""
    return url


def stream_url(url: str, base: str = "") -> str:
    result = normalize_url(url, base)
    return result if result and STREAM_MARKER.search(urlparse(result).path) else ""


def canonical_url(url: str) -> str:
    """Ignore analytics query params, but preserve stream authorization tokens."""
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path,
                       "", urlencode(sorted(query)), ""))


def discover_hls(html: str, base: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for el in soup.find_all(True):
        for key in ("src", "data-src", "data-url", "data-stream", "data-hls", "href"):
            if el.has_attr(key):
                candidate = stream_url(str(el.get(key)), base)
                if candidate:
                    urls.add(candidate)
    # Also handle URLs assigned inside ordinary JS variables; never evaluate scripts.
    raw = unescape(html).replace("\\/", "/")
    for match in STREAM_RE.finditer(raw):
        candidate = stream_url(match.group(), base)
        if candidate:
            urls.add(candidate)
    return sorted(urls)


def best_logo(html: str, base: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for attr, value in (("property", "og:image"), ("name", "twitter:image"),
                        ("name", "twitter:image:src")):
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            result = normalize_url(tag["content"], base)
            if result:
                return result
    for img in soup.select("img[data-src], img[src]"):
        src = img.get("data-src") or img.get("src")
        if not src or not any(token in (" ".join(img.get("class", [])) + " " + str(img.get("alt", "")) + " " + str(img.get("id", ""))).lower() for token in ("event", "match", "thumbnail", "poster")):
            continue
        url = normalize_url(src, base)
        if url and re.search(r"\.(?:png|webp|jpe?g)(?:\?|$)", url, re.I):
            return url
    return ""


def infer_category(path: str, default: str = "Live Sports") -> str:
    path = path.lower()
    for slug, name in (("soccer", "Football"), ("fighting", "Combat Sports"),
                       ("basketball", "Basketball"), ("nba", "NBA"),
                       ("nfl", "NFL"), ("ncaa", "College Sports"),
                       ("f1", "Formula 1"), ("nhl", "NHL"),
                       ("mlb", "MLB"), ("tennis", "Tennis")):
        if slug in path:
            return name
    return default


def event_links(html: str, base: str, domains: set[str]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for a in soup.select("a[href]"):
        url = normalize_url(a.get("href", ""), base)
        title = clean_name(a.get_text(" ", strip=True))
        if not url or urlparse(url).hostname not in domains or not SANE_LINK.fullmatch(title):
            continue
        if urlparse(url).path in ("", "/"):
            continue
        if EVENT_PATH.search(urlparse(url).path) or a.find_parent("tr") is not None:
            found[url] = title
    return sorted(found.items())


def parse_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Logo overrides must be a JSON object")
    return {event_key(k): str(v) for k, v in data.items() if normalize_url(str(v))}


class Collector:
    def __init__(self, sources: list[str], routes: list[str], *, timeout: int = 12,
                 validate: bool = True, max_event_pages: int = 100):
        self.sources = [s.rstrip("/") for s in sources]
        self.routes = routes
        self.timeout = timeout
        self.validate = validate
        self.max_event_pages = max_event_pages
        self.domains = {urlparse(s).hostname for s in self.sources}
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"})
        self.html_cache: dict[str, str] = {}
        self.status: dict[str, bool] = {}

    def fetch(self, url: str) -> str:
        if url in self.html_cache:
            return self.html_cache[url]
        try:
            response = self.http.get(url, timeout=self.timeout)
            response.raise_for_status()
            if "html" not in response.headers.get("content-type", "text/html").lower():
                return ""
            content = response.text[:2_000_000]
            self.html_cache[url] = content
            return content
        except requests.RequestException as exc:
            LOG.warning("Unable to fetch %s: %s", url, exc)
            return ""

    def is_playable(self, url: str) -> bool:
        if url in self.status:
            return self.status[url]
        if not self.validate:
            self.status[url] = True
            return True
        try:
            response = self.http.get(url, timeout=self.timeout, stream=True,
                                     headers={"Accept": "application/vnd.apple.mpegurl,*/*"})
            response.raise_for_status()
            first_bytes = b""
            for chunk in response.iter_content(chunk_size=512):
                first_bytes += chunk
                if len(first_bytes) >= 512:
                    break
            response.close()
            ok = first_bytes.lstrip().startswith(b"#EXTM3U")
        except requests.RequestException:
            ok = False
        self.status[url] = ok
        return ok

    def collect(self, overrides: dict[str, str]) -> tuple[list[Entry], int]:
        pages: dict[str, tuple[str, str]] = {}
        discovered_index = 0
        for origin in self.sources:
            for route in self.routes:
                index_url = origin + (route if route.startswith("/") else "/" + route)
                html = self.fetch(index_url)
                if not html:
                    continue
                discovered_index += 1
                for page_url, title in event_links(html, index_url, self.domains):
                    category = infer_category(route)
                    if page_url not in pages or pages[page_url][1] == "Live Sports":
                        pages[page_url] = (title, category)
        if not pages:
            LOG.warning("No event pages discovered from %s index pages", discovered_index)
        candidates: list[Entry] = []
        for page_url, (title, category) in list(pages.items())[:self.max_event_pages]:
            html = self.fetch(page_url)
            if not html:
                continue
            event_title = clean_name(title)
            logo = overrides.get(event_key(event_title)) or best_logo(html, page_url)
            urls = discover_hls(html, page_url)
            # Public iframes may contain an HLS source in their HTML. Do not execute
            # scripts, intercept private requests, or circumvent player protections.
            soup = BeautifulSoup(html, "html.parser")
            for iframe in soup.select("iframe[src]")[:8]:
                iframe_url = normalize_url(iframe.get("src"), page_url)
                if iframe_url and urlparse(iframe_url).hostname in self.domains:
                    urls += discover_hls(self.fetch(iframe_url), iframe_url)
            for url in set(urls):
                if self.is_playable(url):
                    candidates.append(Entry(event_title, url, category, logo, page_url))
        # Collapse duplicates from mirror sites by canonical event name + HLS URL.
        unique: dict[tuple[str, str], Entry] = {}
        for item in candidates:
            unique.setdefault((event_key(item.title), canonical_url(item.url)), item)
        return sorted(unique.values(), key=lambda e: (e.category, e.title.lower(), e.url)), discovered_index


def m3u_escape(value: str) -> str:
    return value.replace('"', "'").replace("\r", " ").replace("\n", " ")


def render_m3u(entries: list[Entry]) -> str:
    groups: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        groups[event_key(entry.title)].append(entry)
    lines = ["#EXTM3U"]
    for items in sorted(groups.values(), key=lambda v: (v[0].category, v[0].title.lower())):
        for i, item in enumerate(sorted(items, key=lambda e: e.url), 1):
            title = item.title + (f" | Stream {i}" if len(items) > 1 else "")
            meta = f'tvg-name="{m3u_escape(item.title)}" tvg-id="{event_key(item.title)}"'
            if item.logo:
                meta += f' tvg-logo="{m3u_escape(item.logo)}"'
            meta += f' group-title="{m3u_escape(item.category)}"'
            lines += [f"#EXTINF:-1 {meta},{m3u_escape(title)}", item.url]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public, playable HLS streams")
    parser.add_argument("--config", default="config/sources.json")
    parser.add_argument("--logos", default="config/logo_overrides.json")
    parser.add_argument("--output", default="playlist.m3u")
    parser.add_argument("--manifest", default="data/manifest.json")
    parser.add_argument("--no-validate", action="store_true", help="Testing only: don't verify HLS content")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    collector = Collector(cfg["sources"], cfg["routes"],
                          timeout=cfg.get("timeout_seconds", 12),
                          validate=not args.no_validate,
                          max_event_pages=cfg.get("max_event_pages", 100))
    entries, index_pages = collector.collect(parse_overrides(Path(args.logos)))
    LOG.info("Fetched %d discovery pages; verified %d unique HLS streams", index_pages, len(entries))
    if not entries:
        # Fail safely; never overwrite a previously working playlist with an empty one.
        raise SystemExit("No verified live HLS feeds discovered. Existing playlist preserved.")
    thumb_dir = Path("assets/thumbnails")
    enriched = []
    used = set()
    for item in entries:
        if item.logo:
            enriched.append(item)
        else:
            generated = create_thumbnail(item.title, item.category, event_key(item.title), thumb_dir)
            used.add(generated.rsplit("/", 1)[-1])
            enriched.append(Entry(item.title, item.url, item.category, generated, item.source_page))
    if thumb_dir.exists():
        for stale in thumb_dir.glob("*.png"):
            if stale.name not in used:
                stale.unlink()
    entries = enriched
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_m3u(entries), encoding="utf-8")
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"updated_at_utc": datetime.now(timezone.utc).isoformat(),
                                    "stream_count": len(entries), "events": len({event_key(e.title) for e in entries}),
                                    "entries": [asdict(e) for e in entries]}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    LOG.info("Wrote %s", out)


if __name__ == "__main__":
    main()
