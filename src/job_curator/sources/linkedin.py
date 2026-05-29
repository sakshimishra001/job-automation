import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from src.job_curator.sources.common import (
    card_text,
    extract_company_apply_url,
    first_attribute,
    first_text,
    infer_country_from_location,
)


logger = logging.getLogger(__name__)

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"
DEFAULT_LOCATION = "India"


def scrape_linkedin_jobs(
    query: str,
    location: str = DEFAULT_LOCATION,
    max_jobs: int = 25,
    headless: bool = True,
) -> list[dict]:
    logger.info("Starting LinkedIn scrape for query: %s", query)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright is not installed. Run `pip install -r requirements.txt` "
            "and then `playwright install chromium`."
        )
        return []

    url = build_search_url(query, location)
    jobs = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()

            logger.info("Opening LinkedIn Jobs search page")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                page.wait_for_selector("a[href*='/jobs/view/']", timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("No LinkedIn job cards found for query: %s", query)
                browser.close()
                return []

            cards = page.locator("li:has(a[href*='/jobs/view/'])")
            card_count = min(cards.count(), max_jobs)
            logger.info("Found %s LinkedIn job cards", card_count)

            for index in range(card_count):
                card = cards.nth(index)
                detail_metadata = extract_job_detail_metadata(page, card, location)
                job = parse_job_card(card, detail_metadata)
                if job:
                    jobs.append(job)

            browser.close()

    except PlaywrightError as error:
        logger.warning("LinkedIn scrape failed for query '%s': %s", query, error)
        return []
    except Exception as error:
        logger.exception("Unexpected LinkedIn scrape failure for query '%s': %s", query, error)
        return []

    logger.info("Scraped %s LinkedIn jobs for query: %s", len(jobs), query)
    return jobs


def build_search_url(query: str, location: str) -> str:
    return (
        f"{LINKEDIN_JOBS_URL}?keywords={quote_plus(query)}"
        f"&location={quote_plus(location)}"
        "&start=0"
    )


def parse_job_card(card, detail_metadata: dict[str, str] | None = None) -> dict | None:
    detail_metadata = detail_metadata or {}
    search_text = card_text(card)
    detail_text = detail_metadata.get("detail_text", "")
    title = first_text(
        card,
        [
            "h3",
            ".base-search-card__title",
            ".job-search-card__title",
        ],
    )
    employer = first_text(
        card,
        [
            "h4",
            ".base-search-card__subtitle",
            ".job-search-card__subtitle",
        ],
    )
    location = first_text(
        card,
        [
            ".job-search-card__location",
            ".base-search-card__metadata",
        ],
    )
    if not location:
        location = detail_metadata.get("location", "")
    apply_link = first_attribute(card, "a[href*='/jobs/view/']", "href")
    clean_apply_link = clean_linkedin_url(apply_link)
    posted_date = first_attribute(card, "time", "datetime") or first_text(card, ["time"])

    if not title or not apply_link:
        return None

    employment_type = detail_metadata.get("employment_type", "")
    workplace_type_raw = detail_metadata.get("workplace_type", "")

    return {
        "job_title": title,
        "employer_name": employer,
        "job_city": location,
        "job_state": "",
        "job_country": infer_country_from_location(location),
        "job_location": location,
        "job_employment_type": employment_type,
        "job_workplace_type_raw": workplace_type_raw,
        "job_posted_at_datetime_utc": posted_date,
        "job_apply_link": clean_apply_link,
        "company_apply_url": extract_company_apply_url(clean_apply_link, ["linkedin.com"]),
        "job_publisher": "LinkedIn",
        "job_description": detail_text,
        "job_search_text": " ".join(part for part in [search_text, detail_text] if part).strip(),
        "search_location_context": detail_metadata.get("search_location_context", DEFAULT_LOCATION),
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def extract_job_detail_metadata(page, card, search_location_context: str) -> dict[str, str]:
    detail_text = ""
    workplace_type = ""
    employment_type = ""
    location = ""

    try:
        card.locator("a[href*='/jobs/view/']").first.click(timeout=5000)
        wait_for_job_detail_panel(page)
        top_card_metadata = extract_top_card_metadata(page)
        detail_text = collect_detail_text(page)
        location = top_card_metadata.get("location", "") or extract_location_from_text(detail_text)
        workplace_type = top_card_metadata.get("workplace_type", "") or extract_workplace_type_metadata(page, detail_text)
        employment_type = top_card_metadata.get("employment_type", "") or extract_employment_type_from_text(detail_text)
    except Exception as error:
        logger.debug("Could not extract LinkedIn detail metadata: %s", error)

    return {
        "detail_text": detail_text,
        "location": location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
        "search_location_context": search_location_context,
    }


def collect_detail_text(page) -> str:
    selectors = [
        ".description__job-criteria-list",
        ".description__job-criteria-item",
        ".description__text",
        ".show-more-less-html__markup",
        ".job-details-jobs-unified-top-card__job-insight",
        ".job-details-jobs-unified-top-card__job-insight-view-model-secondary",
        ".job-details-jobs-unified-top-card__primary-description",
        ".job-details-jobs-unified-top-card__tertiary-description",
        ".jobs-unified-top-card__job-insight",
        ".jobs-unified-top-card__subtitle-primary-grouping",
    ]
    return " ".join(collect_unique_texts(page, selectors))


def extract_workplace_type_metadata(page, detail_text: str) -> str:
    workplace_type = extract_workplace_type_from_criteria_items(page)
    if workplace_type:
        return workplace_type

    selectors = [
        ".description__job-criteria-item",
        ".job-details-jobs-unified-top-card__job-insight",
        ".job-details-jobs-unified-top-card__job-insight-view-model-secondary",
        ".job-details-jobs-unified-top-card__tertiary-description",
        ".jobs-unified-top-card__job-insight",
        ".artdeco-pill",
        "button[aria-label*='Hybrid']",
        "button[aria-label*='Remote']",
        "button[aria-label*='On-site']",
    ]
    candidate_texts = collect_unique_texts(page, selectors)

    workplace_type = extract_workplace_type_from_lines(candidate_texts)
    if workplace_type:
        return workplace_type

    return extract_workplace_type_from_text(detail_text)


def extract_top_card_metadata(page) -> dict[str, str]:
    location = ""
    workplace_type = ""
    employment_type = ""

    location_selectors = [
        ".job-details-jobs-unified-top-card__primary-description",
        ".jobs-unified-top-card__primary-description",
        ".jobs-unified-top-card__subtitle-primary-grouping",
        ".job-details-jobs-unified-top-card__tertiary-description",
    ]
    badge_selectors = [
        ".job-details-jobs-unified-top-card__content-container .artdeco-pill",
        ".jobs-unified-top-card__content-container .artdeco-pill",
        ".job-details-jobs-unified-top-card__content-container button",
        ".jobs-unified-top-card__content-container button",
    ]

    location_texts = collect_unique_texts(page, location_selectors)
    for value in location_texts:
        extracted_location = extract_location_from_text(value)
        if extracted_location:
            location = extracted_location
            break

    badge_texts = collect_unique_texts(page, badge_selectors)
    for value in badge_texts:
        workplace_candidate = normalize_workplace_type_token(value)
        if workplace_candidate and not workplace_type:
            workplace_type = workplace_candidate

        employment_candidate = extract_employment_type_from_text(value)
        if employment_candidate and not employment_type:
            employment_type = employment_candidate

    return {
        "location": location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
    }


def extract_workplace_type_from_criteria_items(page) -> str:
    selectors = [
        ".description__job-criteria-list li",
        ".description__job-criteria-item",
    ]

    for selector in selectors:
        try:
            items = page.locator(selector)
            count = min(items.count(), 10)
        except Exception:
            continue

        for index in range(count):
            try:
                item_text = items.nth(index).inner_text(timeout=1000).strip()
            except Exception:
                continue

            if not item_text:
                continue

            normalized_item = " ".join(split_metadata_lines(item_text))
            if "workplace type" not in normalized_item:
                continue

            workplace_type = extract_workplace_type_from_text(item_text)
            if workplace_type:
                return workplace_type

            tokens = split_metadata_lines(item_text)
            for token in tokens:
                workplace_type = normalize_workplace_type_token(token)
                if workplace_type:
                    return workplace_type

    return ""


def collect_unique_texts(page, selectors: list[str]) -> list[str]:
    parts = []

    for selector in selectors:
        try:
            texts = page.locator(selector).all_inner_texts()
        except Exception:
            continue

        for text in texts:
            cleaned = str(text).strip()
            if cleaned and cleaned not in parts:
                parts.append(cleaned)

    return parts


def wait_for_job_detail_panel(page) -> None:
    selectors = [
        ".description__job-criteria-list",
        ".job-details-jobs-unified-top-card__job-insight",
        ".jobs-unified-top-card__job-insight",
        ".show-more-less-html__markup",
    ]

    for selector in selectors:
        try:
            page.wait_for_selector(selector, timeout=2500)
            break
        except Exception:
            continue

    page.wait_for_timeout(800)


def extract_workplace_type_from_lines(values: list[str]) -> str:
    normalized_values = []
    for value in values:
        normalized_values.extend(split_metadata_lines(value))

    explicit_matches = []
    for value in normalized_values:
        workplace_type = normalize_workplace_type_token(value)
        if workplace_type:
            explicit_matches.append(workplace_type)

    if "Hybrid" in explicit_matches:
        return "Hybrid"
    if "Remote" in explicit_matches:
        return "Remote"
    if "Onsite" in explicit_matches:
        return "Onsite"

    for index, value in enumerate(normalized_values):
        if value == "workplace type" and index + 1 < len(normalized_values):
            workplace_type = normalize_workplace_type_token(normalized_values[index + 1])
            if workplace_type:
                return workplace_type

    return ""


def extract_workplace_type_from_text(text: str) -> str:
    for value in split_metadata_lines(text):
        workplace_type = normalize_workplace_type_token(value)
        if workplace_type:
            return workplace_type
    return ""


def extract_employment_type_from_text(text: str) -> str:
    clean = str(text).strip().lower()
    if not clean:
        return ""

    match = re.search(
        r"\b(full[- ]time|part[- ]time|contract|temporary|internship|intern|freelance)\b",
        clean,
    )
    if not match:
        return ""

    return match.group(1).replace("-", " ").title()


def split_metadata_lines(text: str) -> list[str]:
    clean_text = str(text).replace("Â·", "·")
    chunks = re.split(r"[\n\r\u00b7•|]+", clean_text)
    values = []
    for chunk in chunks:
        cleaned = chunk.strip().lower()
        if cleaned:
            values.append(cleaned)
    return values


def normalize_workplace_type_token(value: str) -> str:
    clean = str(value).strip().lower()
    if not clean:
        return ""

    if re.search(r"\b(remote|fully remote|remote work|work remotely)\b", clean):
        return "Remote"
    if re.search(r"\bhybrid\b", clean):
        return "Hybrid"
    if re.search(r"\b(on-site|onsite|on site)\b", clean):
        return "Onsite"
    return ""


def extract_location_from_text(text: str) -> str:
    clean = str(text).strip()
    if not clean:
        return ""

    for chunk in clean.split("  "):
        candidate = chunk.strip()
        if "·" in candidate:
            left = candidate.split("·", 1)[0].strip()
            if looks_like_location(left):
                return left
        if looks_like_location(candidate):
            return candidate

    return ""


def looks_like_location(text: str) -> bool:
    clean = str(text).strip().lower()
    if not clean:
        return False

    return any(
        keyword in clean
        for keyword in [
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
            "remote",
            "worldwide",
        ]
    )


def clean_linkedin_url(url: str) -> str:
    if not url:
        return ""

    return url.split("?")[0]
