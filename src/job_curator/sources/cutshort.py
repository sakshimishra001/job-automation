import logging
import re
from urllib.parse import quote_plus

from src.job_curator.sources.common import (
    extract_company_apply_url,
    infer_country_from_location,
    normalize_url,
    utc_timestamp,
)


logger = logging.getLogger(__name__)

CUTSHORT_BASE_URL = "https://cutshort.io"


def scrape_cutshort_jobs(
    query: str,
    location: str = "India",
    max_jobs: int = 10,
    headless: bool = True,
) -> list[dict]:
    logger.info("Starting Cutshort scrape for query: %s", query)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright is not installed")
        return []

    url = build_search_url(query)
    jobs = []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
                )
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            try:
                page.wait_for_selector("h2", timeout=10000)
            except PlaywrightTimeoutError:
                logger.warning("No Cutshort job cards found for query: %s", query)
                browser.close()
                return []

            records = extract_job_records(page, max_jobs)
            for record in records:
                job = parse_job_record(record, location)
                if job:
                    jobs.append(job)

            browser.close()
    except PlaywrightError as error:
        logger.warning("Cutshort scrape failed for query '%s': %s", query, error)
        return []
    except Exception as error:
        logger.exception("Unexpected Cutshort scrape failure for query '%s': %s", query, error)
        return []

    logger.info("Scraped %s Cutshort jobs for query: %s", len(jobs), query)
    return jobs


def build_search_url(query: str) -> str:
    return f"{CUTSHORT_BASE_URL}/jobs?search={quote_plus(query)}"


def extract_job_records(page, max_jobs: int) -> list[dict]:
    return page.evaluate(
        """
        (maxJobs) => {
            const seen = new Set();
            const records = [];
            const anchors = Array.from(document.querySelectorAll("a[href*='/job/']"));

            for (const anchor of anchors) {
                const link = anchor.href || "";
                if (!link || seen.has(link)) {
                    continue;
                }
                seen.add(link);

                const text = (anchor.innerText || "").trim();
                const title = extractTitle(anchor, text);
                if (!title || isNonJobTitle(title)) {
                    continue;
                }

                records.push({
                    title,
                    company: extractCompany(anchor, text),
                    link,
                    text,
                });

                if (records.length >= maxJobs) {
                    break;
                }
            }

            return records;
        }

        function extractTitle(anchor, text) {
            const heading = anchor.querySelector("h2");
            if (heading && heading.innerText) {
                return heading.innerText.trim();
            }

            const lines = text.split("\\n").map((line) => line.trim()).filter(Boolean);
            return lines[0] || "";
        }

        function extractCompany(anchor, text) {
            const heading = anchor.querySelector("h3");
            if (heading && heading.innerText) {
                return heading.innerText.trim();
            }

            const lines = text.split("\\n").map((line) => line.trim()).filter(Boolean);
            for (const line of lines) {
                if (line.toLowerCase().startsWith("at ")) {
                    return line;
                }
            }

            let node = anchor;
            for (let level = 0; node && level < 5; level += 1, node = node.parentElement) {
                const companyHeading = node.querySelector && node.querySelector("h3");
                if (companyHeading && companyHeading.innerText) {
                    return companyHeading.innerText.trim();
                }
            }
            return "";
        }

        function isNonJobTitle(title) {
            const clean = title.toLowerCase();
            return [
                "jobs by categories",
                "latest jobs categories",
                "featured jobs",
                "showing ",
                "product management jobs",
            ].some((prefix) => clean.startsWith(prefix));
        }
        """,
        max_jobs,
    )


def extract_job_records_from_headings(page, max_jobs: int) -> list[dict]:
    return page.evaluate(
        """
        (maxJobs) => Array.from(document.querySelectorAll("h2")).slice(0, maxJobs).map((titleNode) => {
            let text = "";
            let link = "";
            let node = titleNode;

            for (let level = 0; node && level < 8; level += 1, node = node.parentElement) {
                const anchor = node.querySelector && node.querySelector("a[href*='/job']");
                if (anchor && !link) {
                    link = anchor.href;
                }

                const candidateText = (node.innerText || "").trim();
                if (candidateText.length > text.length) {
                    text = candidateText;
                }

                if (link && text.length > 250) {
                    break;
                }
            }

            return {
                title: (titleNode.innerText || "").trim(),
                company: extractCompany(titleNode),
                link,
                text,
            };
        }).filter((record) => record.title && record.link);

        function extractCompany(titleNode) {
            let node = titleNode;
            for (let level = 0; node && level < 6; level += 1, node = node.parentElement) {
                const heading = node.querySelector && node.querySelector("h3");
                if (heading && heading.innerText) {
                    return heading.innerText.trim();
                }
            }
            return "";
        }
        """,
        max_jobs,
    )


def parse_job_record(record: dict, search_location_context: str) -> dict | None:
    title = str(record.get("title", "")).strip()
    apply_link = normalize_url(str(record.get("link", "")).strip(), CUTSHORT_BASE_URL)
    search_text = normalize_text(str(record.get("text", "")).strip())

    if not title or not apply_link:
        return None

    employer = clean_company_name(str(record.get("company", "")).strip())
    location = extract_location(search_text) or search_location_context
    posted_date = extract_posted_date(search_text)

    return {
        "job_title": title,
        "employer_name": employer,
        "job_city": location,
        "job_state": "",
        "job_country": infer_country_from_location(location or search_location_context),
        "job_location": location,
        "job_employment_type": extract_employment_type(search_text),
        "job_posted_at_datetime_utc": posted_date,
        "job_apply_link": apply_link,
        "company_apply_url": extract_company_apply_url(
            apply_link,
            ["cutshort.io", "www.cutshort.io"],
        ),
        "job_publisher": "Cutshort",
        "job_description": search_text,
        "job_search_text": search_text,
        "search_location_context": search_location_context,
        "fetched_at": utc_timestamp(),
    }


def clean_company_name(value: str) -> str:
    clean = value.strip()
    if clean.lower().startswith("at "):
        return clean[3:].strip()
    return clean


def normalize_text(value: str) -> str:
    return " ".join(line.strip() for line in value.splitlines() if line.strip())


def extract_location(text: str) -> str:
    known_locations = [
        "Bengaluru",
        "Bangalore",
        "Gurugram",
        "Gurgaon",
        "Mumbai",
        "Pune",
        "Hyderabad",
        "Chennai",
        "Noida",
        "Delhi",
        "Ahmedabad",
        "Jaipur",
        "Indore",
        "Coimbatore",
        "Kochi",
        "Bhubaneswar",
        "Lucknow",
        "Visakhapatnam",
        "Work From Home",
        "Remote",
        "India",
    ]
    for location in known_locations:
        if re.search(rf"\b{re.escape(location)}\b", text, re.IGNORECASE):
            return location
    return ""


def extract_employment_type(text: str) -> str:
    match = re.search(r"\b(full[- ]time|part[- ]time|contract|internship)\b", text, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).replace("-", " ").title()


def extract_posted_date(text: str) -> str:
    match = re.search(r"\b(\d+\s+(?:hour|day|week|month)s?\s+ago|today|yesterday)\b", text, re.IGNORECASE)
    return match.group(1) if match else ""
