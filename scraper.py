"""
Core scraping logic for Aryx Prospector.

Shared by both the CLI script (aryx_prospector.py) and the web app (app.py).
No paid APIs are used - only requests and BeautifulSoup4.
"""

import re
import time
import warnings
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

warnings.simplefilter("ignore", InsecureRequestWarning)

REQUEST_TIMEOUT = (5, 10)  # (connect, read) seconds for the homepage
PAGE_TIMEOUT = (3, 6)  # shorter timeout for secondary pages, so one slow
                       # page can't stall the whole crawl
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9.\-+_]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

FALSE_POSITIVE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".bmp", ".ico", ".tiff", ".avif",
)

# Non-HTML assets we won't bother fetching as "other pages".
NON_PAGE_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
    ".ico", ".tiff", ".avif", ".zip", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".mp4", ".mp3", ".css", ".js", ".json", ".xml",
)

# Pages most likely to list a contact email, checked first.
PRIORITY_KEYWORDS = (
    "contact", "about", "team", "staff", "support", "connect",
    "reach", "touch", "info", "help", "location",
)

MAX_PAGES_TO_CRAWL = 6  # beyond the homepage
CRAWL_TIME_BUDGET_SECONDS = 20  # stop following links past this


def is_valid_email(candidate: str) -> bool:
    lowered = candidate.lower()
    if lowered.endswith(FALSE_POSITIVE_EXTENSIONS):
        return False
    if any(ext in lowered for ext in FALSE_POSITIVE_EXTENSIONS):
        return False
    return True


def normalize_url(raw_url: str) -> str:
    url = str(raw_url).strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def extract_email_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        if href.lower().startswith("mailto:"):
            email = href[len("mailto:"):].split("?")[0].strip()
            if email and is_valid_email(email):
                return email

    # Many small-business sites (page builders, SEO plugins) embed their
    # contact email in a JSON-LD <script type="application/ld+json"> block
    # for Google's LocalBusiness schema, with no matching visible text or
    # mailto link anywhere on the page. BeautifulSoup's get_text() skips
    # script content entirely, so this needs its own targeted pass - scoped
    # to just this script type (not all <script> tags) to avoid picking up
    # unrelated hex IDs from analytics/error-tracking snippets.
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        for match in EMAIL_REGEX.findall(script.string):
            if is_valid_email(match):
                return match

    page_text = soup.get_text(separator=" ")
    matches = EMAIL_REGEX.findall(page_text)
    for match in matches:
        if is_valid_email(match):
            return match

    return ""


def _fetch(url: str, timeout) -> tuple[str, str]:
    """Returns (html, error_message). html is '' on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, verify=False)
        response.raise_for_status()
        return response.text, ""
    except requests.RequestException as exc:
        return "", str(exc)


def _find_internal_links(base_url: str, html: str, limit: int) -> list[str]:
    """Same-domain links worth checking, contact/about-like pages first."""
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc

    seen = {base_url}
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute = urljoin(base_url, href).split("#")[0]
        if absolute in seen:
            continue
        seen.add(absolute)

        parsed = urlparse(absolute)
        if parsed.netloc != base_netloc:
            continue
        if absolute.lower().endswith(NON_PAGE_EXTENSIONS):
            continue

        candidates.append(absolute)

    def priority(link: str) -> int:
        path = urlparse(link).path.lower()
        for i, keyword in enumerate(PRIORITY_KEYWORDS):
            if keyword in path:
                return i
        return len(PRIORITY_KEYWORDS)

    candidates.sort(key=priority)
    return candidates[:limit]


def scrape_email(url: str) -> tuple[str, str]:
    """
    Checks the homepage first, then - if no email is found there - follows
    same-domain links (prioritizing Contact/About/Team-style pages) up to
    MAX_PAGES_TO_CRAWL pages or CRAWL_TIME_BUDGET_SECONDS, whichever comes
    first. Returns (email, error_message); error_message is '' on success
    or when the homepage loaded but no email was found anywhere crawled.
    """
    html, error = _fetch(url, REQUEST_TIMEOUT)
    if not html:
        return "", error

    email = extract_email_from_html(html)
    if email:
        return email, ""

    try:
        candidates = _find_internal_links(url, html, MAX_PAGES_TO_CRAWL)
    except Exception:
        candidates = []

    start = time.monotonic()
    for link in candidates:
        if time.monotonic() - start > CRAWL_TIME_BUDGET_SECONDS:
            break

        page_html, _ = _fetch(link, PAGE_TIMEOUT)
        if not page_html:
            continue

        email = extract_email_from_html(page_html)
        if email:
            return email, ""

    return "", ""
