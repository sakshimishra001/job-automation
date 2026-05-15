import logging
from urllib.parse import quote_plus

from src.job_curator.sources.common import (
    first_attribute,
    first_text,
    normalize_url,
    parse_posted_date,
    utc_timestamp,
)


logger = logging.getLogger(__name__)

GLASSDOOR_BASE_URL = "https://www.glassdoor.co.in"


def scrape_glassdoor_jobs(
    query: str,
    location: str = "India",
    max_jobs: int = 10,
    headless: bool = True,
) -> list[dict]:
    logger.info("Starting Glassdoor scrape for query: %s", query)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright is not installed")
        return []

    url = build_search_url(query, location)
    jobs = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                page.wait_for_selector("a[href*='job-listing']", timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("No Glassdoor job cards found for query: %s", query)
                browser.close()
                return []

            cards = page.locator("li[data-test='jobListing'], [data-test='jobListing']")
            for index in range(min(cards.count(), max_jobs)):
                job = parse_job_card(cards.nth(index))
                if job:
                    jobs.append(job)

            browser.close()
    except PlaywrightError as error:
        logger.warning("Glassdoor scrape failed for query '%s': %s", query, error)
        return []

    logger.info("Scraped %s Glassdoor jobs for query: %s", len(jobs), query)
    return jobs


def build_search_url(query: str, location: str) -> str:
    return (
        f"{GLASSDOOR_BASE_URL}/Job/jobs.htm"
        f"?sc.keyword={quote_plus(query)}&locKeyword={quote_plus(location)}"
        "&fromAge=7"
    )


def parse_job_card(card) -> dict | None:
    title = first_text(card, ["[data-test='job-title']", "a[href*='job-listing']"])
    employer = first_text(card, ["[data-test='employer-name']", ".EmployerProfile_compactEmployerName__9MGcV"])
    location = first_text(card, ["[data-test='job-location']"])
    apply_link = first_attribute(card, "a[href*='job-listing']", "href")
    posted_date = parse_posted_date(first_text(card, ["[data-test='job-age']"]))

    if not title or not apply_link:
        return None

    return {
        "job_title": title,
        "employer_name": employer,
        "job_city": location or "India",
        "job_state": "",
        "job_country": "IN",
        "job_location": location or "India",
        "job_employment_type": "",
        "job_posted_at_datetime_utc": posted_date,
        "job_apply_link": normalize_url(apply_link, GLASSDOOR_BASE_URL),
        "job_publisher": "Glassdoor",
        "job_description": "",
        "fetched_at": utc_timestamp(),
    }
