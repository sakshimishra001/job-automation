from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = Exception


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def first_text(card, selectors: list[str]) -> str:
    for selector in selectors:
        locator = card.locator(selector).first
        try:
            if locator.count() > 0:
                return locator.inner_text(timeout=1000).strip()
        except PlaywrightError:
            continue

    return ""


def first_attribute(card, selector: str, attribute: str) -> str:
    locator = card.locator(selector).first
    try:
        if locator.count() > 0:
            value = locator.get_attribute(attribute, timeout=1000)
            return value.strip() if value else ""
    except PlaywrightError:
        return ""

    return ""


def card_text(card) -> str:
    try:
        return card.inner_text(timeout=1000).strip()
    except PlaywrightError:
        return ""


def normalize_url(url: str, base_url: str) -> str:
    if not url:
        return ""

    clean_url = url.split("?")[0]
    if clean_url.startswith("http"):
        return clean_url
    if clean_url.startswith("/"):
        return f"{base_url.rstrip('/')}{clean_url}"

    return clean_url


def extract_company_apply_url(url: str, wrapper_domains: list[str]) -> str:
    normalized = normalize_url(url, "")
    if not normalized:
        return ""

    parsed = urlparse(normalized)
    host = parsed.netloc.lower().replace("www.", "")
    if not host:
        return ""

    if host in {domain.lower().replace("www.", "") for domain in wrapper_domains}:
        return ""

    return normalized


def parse_posted_date(value: str) -> str:
    text = (value or "").strip().lower()
    now = datetime.now(timezone.utc)

    if not text:
        return ""
    if "today" in text or "just" in text:
        return now.date().isoformat()
    if "yesterday" in text:
        return (now - timedelta(days=1)).date().isoformat()

    number = first_integer(text)
    if number is None:
        return value.strip()

    if "hour" in text:
        return (now - timedelta(hours=number)).date().isoformat()
    if "day" in text:
        return (now - timedelta(days=number)).date().isoformat()
    if "week" in text:
        return (now - timedelta(weeks=number)).date().isoformat()

    return value.strip()


def first_integer(text: str) -> int | None:
    digits = ""
    for character in text:
        if character.isdigit():
            digits += character
        elif digits:
            break

    return int(digits) if digits else None


def infer_country_from_location(location: str) -> str:
    clean = str(location).strip().lower()
    if not clean:
        return ""

    india_keywords = [
        "india",
        "bangalore",
        "bengaluru",
        "mumbai",
        "pune",
        "hyderabad",
        "gurgaon",
        "gurugram",
        "chennai",
        "noida",
        "karnataka",
        "tamil nadu",
        "maharashtra",
        "telangana",
        "ahmedabad",
        "jaipur",
        "indore",
        "coimbatore",
        "kochi",
        "bhubaneswar",
        "lucknow",
        "visakhapatnam",
    ]
    if any(keyword in clean for keyword in india_keywords):
        return "India"

    non_india_keywords = [
        "united states",
        "usa",
        "uk",
        "united kingdom",
        "singapore",
        "dubai",
        "uae",
        "australia",
        "canada",
        "germany",
        "netherlands",
        "ireland",
        "france",
        "spain",
        "japan",
        "saudi arabia",
        "qatar",
        "new zealand",
        "hong kong",
        "poland",
    ]
    for keyword in non_india_keywords:
        if keyword in clean:
            return keyword.title()

    return ""
