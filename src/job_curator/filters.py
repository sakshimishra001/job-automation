import logging


logger = logging.getLogger(__name__)

TRUSTED_PUBLISHERS = [
    "linkedin",
    "indeed",
    "glassdoor",
    "naukri",
]

INDIA_LOCATION_WORDS = [
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
]


def keep_india_jobs(jobs: list[dict]) -> list[dict]:
    kept_jobs = []

    for job in jobs:
        if is_india_job(job):
            kept_jobs.append(job)

    logger.info("Kept %s India-focused jobs", len(kept_jobs))
    logger.info("Rejected %s non-India jobs", len(jobs) - len(kept_jobs))

    return kept_jobs


def keep_approved_publishers(jobs: list[dict]) -> list[dict]:
    kept_jobs = []

    for job in jobs:
        if is_approved_publisher(job):
            kept_jobs.append(job)

    logger.info("Kept %s jobs from approved publishers", len(kept_jobs))
    logger.info("Rejected %s jobs from unapproved publishers", len(jobs) - len(kept_jobs))

    return kept_jobs


def is_india_job(job: dict) -> bool:
    location_text = " ".join(
        [
            clean_text(job.get("job_city", "")),
            clean_text(job.get("job_state", "")),
            clean_text(job.get("job_country", "")),
            clean_text(job.get("job_location", "")),
        ]
    )

    return contains_any(location_text, INDIA_LOCATION_WORDS)


def is_approved_publisher(job: dict) -> bool:
    publisher = clean_text(job.get("job_publisher", ""))
    apply_link = clean_text(job.get("job_apply_link", ""))

    return contains_any(publisher, TRUSTED_PUBLISHERS) or contains_any(
        apply_link,
        TRUSTED_PUBLISHERS,
    )


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
