import logging
from urllib.parse import quote_plus

from src.job_curator.sources.common import (
    card_text,
    extract_company_apply_url,
    first_attribute,
    first_text,
    infer_country_from_location,
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
                job = parse_job_card(cards.nth(index), location)
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


def parse_job_card(card, search_location_context: str) -> dict | None:
    search_text = card_text(card)
    title = first_text(card, ["[data-test='job-title']", "a[href*='job-listing']"])
    employer = first_text(card, ["[data-test='employer-name']", ".EmployerProfile_compactEmployerName__9MGcV"])
    location = first_text(card, ["[data-test='job-location']"])
    apply_link = first_attribute(card, "a[href*='job-listing']", "href")
    normalized_apply_link = normalize_url(apply_link, GLASSDOOR_BASE_URL)
    posted_date = parse_posted_date(first_text(card, ["[data-test='job-age']"]))

    if not title or not apply_link:
        return None

    return {
        "job_title": title,
        "employer_name": employer,
        "job_city": location or "India",
        "job_state": "",
        "job_country": infer_country_from_location(location or search_location_context),
        "job_location": location or "India",
        "job_employment_type": "",
        "job_posted_at_datetime_utc": posted_date,
        "job_apply_link": normalized_apply_link,
        "company_apply_url": extract_company_apply_url(
            normalized_apply_link,
            ["glassdoor.com", "glassdoor.co.in", "www.glassdoor.co.in"],
        ),
        "job_publisher": "Glassdoor",
        "job_description": "",
        "job_search_text": search_text,
        "search_location_context": search_location_context,
        "fetched_at": utc_timestamp(),
    }
