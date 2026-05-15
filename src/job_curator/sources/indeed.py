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

INDEED_BASE_URL = "https://in.indeed.com"


def scrape_indeed_jobs(
    query: str,
    location: str = "India",
    max_jobs: int = 10,
    headless: bool = True,
) -> list[dict]:
    logger.info("Starting Indeed scrape for query: %s", query)

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
                page.wait_for_selector("a[href*='/rc/clk'], a[href*='/pagead/']", timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning("No Indeed job cards found for query: %s", query)
                browser.close()
                return []

            cards = page.locator("[data-testid='slider_item'], .job_seen_beacon")
            for index in range(min(cards.count(), max_jobs)):
                job = parse_job_card(cards.nth(index))
                if job:
                    jobs.append(job)

            browser.close()
    except PlaywrightError as error:
        logger.warning("Indeed scrape failed for query '%s': %s", query, error)
        return []

    logger.info("Scraped %s Indeed jobs for query: %s", len(jobs), query)
    return jobs


def build_search_url(query: str, location: str) -> str:
    return (
        f"{INDEED_BASE_URL}/jobs"
        f"?q={quote_plus(query)}&l={quote_plus(location)}&fromage=7"
    )


def parse_job_card(card) -> dict | None:
    title = first_text(card, ["h2", "[data-testid='jobTitle']", ".jobTitle"])
    employer = first_text(card, ["[data-testid='company-name']", ".companyName"])
    location = first_text(card, ["[data-testid='text-location']", ".companyLocation"])
    apply_link = first_attribute(card, "a[href*='/rc/clk'], a[href*='/pagead/']", "href")
    posted_date = parse_posted_date(first_text(card, ["[data-testid='myJobsStateDate']", ".date"]))

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
        "job_apply_link": normalize_url(apply_link, INDEED_BASE_URL),
        "job_publisher": "Indeed",
        "job_description": "",
        "fetched_at": utc_timestamp(),
    }
