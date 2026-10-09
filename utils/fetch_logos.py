#!/usr/bin/env python3
"""Fetch a logo for every conference from its official website.

Candidates are tried in priority order: apple-touch-icon, og:image, an
<img> whose src/class/alt mentions "logo", then the favicon.  Anything
that decodes to at least MIN_SIZE pixels is saved as a square PNG under
static/img/logos/<id>.png; conferences with no usable image get a
generated acronym badge in the colour of their first subject tag.
"""

from __future__ import annotations

import concurrent.futures
import re
import sys
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CONFERENCES_FILE = ROOT / "_data" / "conferences.yml"
TYPES_FILE = ROOT / "_data" / "types.yml"
LOGO_DIR = ROOT / "static" / "img" / "logos"
WEBP_DIR = ROOT / "static" / "img" / "logos-webp"
UA = "Mozilla/5.0 (Paper-deadlines logo fetcher)"
MIN_SIZE = 48
BADGE_SIZE = 256


def own_logo_webp(html: str, conf: dict) -> str | None:
    """Conference Catalysts sites (dac.com, iccad.com, ...) serve the
    conference's own logo as webp under glide-cache/containers/logos/,
    named like "<id>-logo-hr_color-...".  Sponsor logos live there too,
    so require the conference short name in the file name and prefer
    the high-resolution variant."""
    short = re.sub(r"[^a-z]", "", conf["title"].lower())
    found = []
    for url in re.findall(r"[A-Za-z0-9_:%().\\-/]+\.webp", html):
        name = url.rsplit("/", 1)[-1].lower()
        if "logo" in name and short in name:
            found.append((0 if "-hr_" in name else 1, url))
    return sorted(found)[0][1] if found else None


def fetch(conf_url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(conf_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_page(conf_url: str) -> tuple[str, str]:
    """Return the visible-free raw HTML plus the final URL after redirects,
    so relative image paths resolve against where the site really lives."""
    request = urllib.request.Request(conf_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace"), response.geturl()


def candidates(html: str, base: str) -> list[str]:
    found: list[tuple[int, str]] = []

    def add(priority: int, url: str) -> None:
        if url and not url.startswith("data:"):
            found.append((priority, urllib.parse.urljoin(base, url)))

    for attr in re.findall(r'<link[^>]+rel=["\']apple-touch-icon[^"\']*["\'][^>]*>', html, re.I):
        add(0, (re.search(r'href=["\']([^"\']+)["\']', attr) or [None, ""])[1])
    for tag in re.findall(r'<meta[^>]+property=["\']og:image["\'][^>]*>', html, re.I):
        add(1, (re.search(r'content=["\']([^"\']+)["\']', tag) or [None, ""])[1])
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        if re.search(r'logo', tag, re.I):
            add(2, (re.search(r'src=["\']([^"\']+)["\']', tag) or [None, ""])[1])
    for tag in re.findall(r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]*>', html, re.I):
        if "apple" not in tag.lower():
            add(3, (re.search(r'href=["\']([^"\']+)["\']', tag) or [None, ""])[1])
    # Prefer larger apple-touch-icons (sizes attribute) and drop duplicates.
    seen, ordered = set(), []
    for _, url in sorted(found):
        if url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def normalize(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception:
        return None
    if image.width < MIN_SIZE or image.height < MIN_SIZE:
        return None
    return image.convert("RGBA")


def badge(conf: dict, color: str) -> Image.Image:
    image = Image.new("RGBA", (BADGE_SIZE, BADGE_SIZE), color)
    draw = ImageDraw.Draw(image)
    text = re.sub(r"[^A-Za-z]", "", conf["title"]).upper()[:5] or conf["id"].upper()
    font = ImageFont.truetype("arial.ttf", 88 if len(text) <= 4 else 70)
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((BADGE_SIZE - box[2] + box[0]) / 2, (BADGE_SIZE - box[3] + box[1]) / 2),
              text, font=font, fill="white")
    return image


def fetch_one(conf: dict, colors: dict[str, str]) -> str:
    dest = LOGO_DIR / f"{conf['id']}.png"
    try:
        html, base = fetch_page(conf["link"])
        webp_url = own_logo_webp(html, conf)
        if webp_url:
            data = fetch(webp_url)
            if Image.open(BytesIO(data)).size[0] >= MIN_SIZE:
                (WEBP_DIR / f"{conf['id']}.webp").write_bytes(data)
                return f"official webp: {webp_url}"
        for url in candidates(html, base)[:6]:
            if url.lower().split("?")[0].endswith(".svg") and "logo" in url.lower():
                (LOGO_DIR / f"{conf['id']}.svg").write_bytes(fetch(url))
                return f"official svg: {url}"
            image = normalize(fetch(url))
            if image:
                image.save(dest)
                return f"official: {url}"
    except Exception as exc:
        pass
    color = colors.get(conf["sub"][0] if isinstance(conf["sub"], list) else conf["sub"], "#333333")
    badge(conf, color).save(dest)
    return "badge (no usable official image)"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append",
                        help="only refresh this conference id (protects manual fixes)")
    args = parser.parse_args()
    conferences = yaml.safe_load(CONFERENCES_FILE.read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only)
        conferences = [c for c in conferences if c["id"] in wanted]
    colors = {t["sub"]: t["color"] for t in yaml.safe_load(TYPES_FILE.read_text(encoding="utf-8"))}
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    WEBP_DIR.mkdir(parents=True, exist_ok=True)
    results, failures = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one, c, colors): c for c in conferences}
        for future in concurrent.futures.as_completed(futures):
            conf = futures[future]
            try:
                results[conf["id"]] = future.result()
            except Exception as exc:
                failures.append(f"{conf['id']}: {exc}")
    for conf in conferences:
        source = results.get(conf["id"], "ERROR")
        print(f"{conf['id']:<12} {source}")
        if "badge" in source or source == "ERROR":
            failures.append(f"{conf['id']}: {source}")
    print(f"\n{len(conferences)} logos in {LOGO_DIR}; {len(failures)} needed the fallback badge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
