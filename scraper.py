"""
Core scraping logic for Aryx Prospector.

Shared by both the CLI script (aryx_prospector.py) and the web app (app.py).
No paid APIs are used - only requests and BeautifulSoup4.
"""

import re
import warnings

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

warnings.simplefilter("ignore", InsecureRequestWarning)

REQUEST_TIMEOUT = (5, 10)  # (connect, read) seconds
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

    page_text = soup.get_text(separator=" ")
    matches = EMAIL_REGEX.findall(page_text)
    for match in matches:
        if is_valid_email(match):
            return match

    return ""


def scrape_email(url: str) -> tuple[str, str]:
    """Returns (email, error_message). error_message is '' on success."""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            verify=False,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return "", str(exc)

    try:
        return extract_email_from_html(response.text), ""
    except Exception as exc:
        return "", str(exc)
