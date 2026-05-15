from datetime import datetime, timedelta, timezone

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


def normalize_url(url: str, base_url: str) -> str:
    if not url:
        return ""

    clean_url = url.split("?")[0]
    if clean_url.startswith("http"):
        return clean_url
    if clean_url.startswith("/"):
        return f"{base_url.rstrip('/')}{clean_url}"

    return clean_url


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
