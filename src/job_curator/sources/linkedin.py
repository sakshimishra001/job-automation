import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus


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
                job = parse_job_card(card)
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


def parse_job_card(card) -> dict | None:
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
    apply_link = first_attribute(card, "a[href*='/jobs/view/']", "href")
    posted_date = first_attribute(card, "time", "datetime") or first_text(card, ["time"])

    if not title or not apply_link:
        return None

    return {
        "job_title": title,
        "employer_name": employer,
        "job_city": location,
        "job_state": "",
        "job_country": "IN",
        "job_location": location,
        "job_employment_type": "",
        "job_posted_at_datetime_utc": posted_date,
        "job_apply_link": clean_linkedin_url(apply_link),
        "job_publisher": "LinkedIn",
        "job_description": "",
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def first_text(card, selectors: list[str]) -> str:
    from playwright.sync_api import Error as PlaywrightError

    for selector in selectors:
        locator = card.locator(selector).first
        try:
            if locator.count() > 0:
                return locator.inner_text(timeout=1000).strip()
        except PlaywrightError:
            continue

    return ""


def first_attribute(card, selector: str, attribute: str) -> str:
    from playwright.sync_api import Error as PlaywrightError

    locator = card.locator(selector).first
    try:
        if locator.count() > 0:
            value = locator.get_attribute(attribute, timeout=1000)
            return value.strip() if value else ""
    except PlaywrightError:
        return ""

    return ""


def clean_linkedin_url(url: str) -> str:
    if not url:
        return ""

    return url.split("?")[0]
