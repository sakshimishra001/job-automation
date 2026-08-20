import logging
import time

import requests
from requests import HTTPError, RequestException

from src.job_curator.sources.cutshort import scrape_cutshort_jobs
from src.job_curator.sources.glassdoor import scrape_glassdoor_jobs
from src.job_curator.sources.indeed import scrape_indeed_jobs
from src.job_curator.sources.linkedin import scrape_linkedin_jobs
from src.job_curator.sources.naukri import scrape_naukri_jobs


logger = logging.getLogger(__name__)

SOURCE_SCRAPERS = {
    "linkedin": scrape_linkedin_jobs,
    "cutshort": scrape_cutshort_jobs,
    "naukri": scrape_naukri_jobs,
    "indeed": scrape_indeed_jobs,
    "glassdoor": scrape_glassdoor_jobs,
}


class RateLimitError(RuntimeError):
    pass


def fetch_jobs(config: dict) -> list[dict]:
    api_config = config["api"]
    search_config = config["search"]
    queries = build_all_search_queries(search_config)

    return fetch_jobs_for_queries(api_config, search_config, queries)


def fetch_jobs_for_queries(
    api_config: dict,
    search_config: dict,
    queries: list,
) -> list[dict]:
    if search_config.get("source", "linkedin") == "linkedin":
        if not queries:
            logger.warning("No queries provided for LinkedIn scraping")
            return []

        return fetch_jobs_from_scrapers(search_config, queries)

    headers = {
        "X-RapidAPI-Key": api_config["key"],
        "X-RapidAPI-Host": api_config["host"],
    }

    all_jobs = []
    pages = int(search_config.get("pages", 1))
    country = search_config.get("country", "in")
    request_delay = float(search_config.get("request_delay_seconds", 1))

    for query_number, query in enumerate(queries, start=1):
        params = {
            "query": query,
            "num_pages": pages,
            "country": country,
            "date_posted": "all",
        }

        logger.info("Fetching query %s/%s: %s", query_number, len(queries), query)

        try:
            response = make_request_with_retry(api_config["base_url"], headers, params)
        except RateLimitError:
            raise
        except RuntimeError as error:
            logger.warning("Skipping query after API error: %s", error)
            continue
        except RequestException as error:
            logger.warning("Skipping query after request error: %s", error)
            continue

        payload = response.json()
        data = payload.get("data", [])
        if isinstance(data, dict):
            jobs = data.get("jobs", [])
        else:
            jobs = data

        logger.info("Fetched %s jobs", len(jobs))
        all_jobs.extend(jobs)
        time.sleep(request_delay)

    logger.info("Fetched %s total jobs before filtering", len(all_jobs))

    return all_jobs


def fetch_jobs_from_scrapers(search_config: dict, queries: list) -> list[dict]:
    source_names = get_enabled_sources(search_config)
    max_jobs = int(search_config.get("max_jobs_per_source_query", 10))
    headless = bool(search_config.get("headless", True))
    request_delay = float(search_config.get("request_delay_seconds", 1))

    all_jobs = []
    total_requests = len(source_names) * len(queries)
    request_number = 0

    for query_input in queries:
        query, location = parse_query_input(query_input, search_config)
        for source_name in source_names:
            request_number += 1
            scraper = SOURCE_SCRAPERS.get(source_name)
            if scraper is None:
                logger.warning("Unknown source configured: %s", source_name)
                continue

            logger.info(
                "Fetching source query %s/%s: source=%s query=%s",
                request_number,
                total_requests,
                source_name,
                query,
            )
            jobs = scraper(
                query,
                location=location,
                max_jobs=max_jobs,
                headless=headless,
            )
            logger.info("Fetched %s jobs from %s", len(jobs), source_name)
            all_jobs.extend(jobs)
            time.sleep(request_delay)

    logger.info("Fetched %s total jobs from scraping sources", len(all_jobs))
    return all_jobs


def get_enabled_sources(search_config: dict) -> list[str]:
    sources = search_config.get("sources")
    if isinstance(sources, dict):
        enabled_sources = sources.get("enabled", [])
        if enabled_sources:
            return [str(source).lower() for source in enabled_sources]

    return [str(search_config.get("source", "linkedin")).lower()]


def build_vertical_queries(search_config: dict, vertical: str) -> list[dict]:
    role_queries = get_query_variants(search_config, vertical)
    locations = search_config.get("locations", [])
    max_queries = int(search_config.get("max_queries_per_vertical", len(role_queries)))
    broad_location = str(search_config.get("source_location", "India"))

    if not role_queries:
        return []

    queries = []
    seen = set()

    for index in range(max_queries):
        role_query = role_queries[index % len(role_queries)]
        location = locations[index % len(locations)] if locations else broad_location
        query_text = f"{role_query} {location}".strip()
        payload = {
            "query": query_text,
            "location": broad_location,
        }
        key = (payload["query"].lower(), payload["location"].lower())
        if key in seen:
            continue
        seen.add(key)
        queries.append(payload)

    for role_query in role_queries:
        broad_query = {
            "query": role_query,
            "location": broad_location,
        }
        key = (broad_query["query"].lower(), broad_query["location"].lower())
        if key not in seen and len(queries) < max_queries:
            seen.add(key)
            queries.append(broad_query)

    return queries[:max_queries]


def get_query_variants(search_config: dict, vertical: str) -> list[str]:
    base_queries = search_config.get("role_queries", {}).get(vertical, [])
    expanded_queries = search_config.get("query_expansions", {}).get(vertical, [])
    priority_queries = search_config.get("seniority_priority_queries", {}).get(vertical, [])

    ordered_queries = []
    seen = set()
    for query in list(priority_queries) + list(base_queries) + list(expanded_queries):
        query_text = str(query).strip()
        if not query_text:
            continue
        lowered = query_text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered_queries.append(query_text)

    return ordered_queries


def build_all_search_queries(search_config: dict) -> list[str]:
    if "queries" in search_config:
        return search_config["queries"]

    role_queries_by_vertical = search_config.get("role_queries", {})
    locations = search_config.get("locations", [])

    queries = []
    for role_queries in role_queries_by_vertical.values():
        for role_query in role_queries:
            for location in locations:
                queries.append(f"{role_query} {location}")

    return queries


def parse_query_input(query_input, search_config: dict) -> tuple[str, str]:
    if isinstance(query_input, dict):
        return (
            str(query_input.get("query", "")),
            str(query_input.get("location", search_config.get("source_location", "India"))),
        )

    return str(query_input), str(search_config.get("source_location", "India"))


def make_request_with_retry(
    url: str,
    headers: dict,
    params: dict,
    max_retries: int = 2,
) -> requests.Response:
    for attempt in range(max_retries + 1):
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=20,
        )

        if response.status_code == 429 and attempt < max_retries:
            wait_seconds = 10 * (attempt + 1)
            logger.warning(
                "Rate limited by API. Waiting %s seconds before retrying.",
                wait_seconds,
            )
            time.sleep(wait_seconds)
            continue

        try:
            response.raise_for_status()
        except HTTPError as error:
            if response.status_code == 403:
                raise RuntimeError(
                    "JSearch returned 403 Forbidden. Check your API key, RapidAPI "
                    "subscription, and JSEARCH_API_HOST."
                ) from error
            if response.status_code == 429:
                raise RateLimitError(
                    "JSearch returned 429 Too Many Requests. Wait a few minutes, "
                    "check your RapidAPI quota, or reduce pages/max_queries_per_vertical "
                    "in config/config.yaml."
                ) from error
            raise

        return response

    raise RuntimeError("JSearch request failed after retries.")
