import logging


logger = logging.getLogger(__name__)

TRUSTED_PUBLISHERS = ["linkedin", "indeed", "glassdoor", "naukri"]

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
    "karnataka",
    "tamil nadu",
    "maharashtra",
    "telangana",
    "delhi",
    "new delhi",
    "ncr",
    "uttar pradesh",
    "haryana",
    "ahmedabad",
    "jaipur",
    "indore",
    "coimbatore",
    "kochi",
    "bhubaneswar",
    "lucknow",
    "visakhapatnam",
    "nagpur",
    "surat",
    "vadodara",
    "thiruvananthapuram",
    "mysuru",
    "mohali",
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


def annotate_location_scope_for_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        if is_india_job(job):
            job["location_scope"] = "India"
        else:
            job["location_scope"] = "Rejected"

    return jobs


def keep_supported_location_scope_jobs(jobs: list[dict]) -> list[dict]:
    kept_jobs = [job for job in jobs if job.get("location_scope") == "India"]
    logger.info("Kept %s India jobs after location scope filtering", len(kept_jobs))
    logger.info("Rejected %s location-mismatched jobs", len(jobs) - len(kept_jobs))
    return kept_jobs


def is_india_job(job: dict) -> bool:
    country = clean_text(job.get("job_country", ""))
    if country in {"in", "india"}:
        return True

    location_text = build_location_text(job)
    context_text = clean_text(job.get("search_location_context", ""))
    searchable_text = " ".join(
        [
            location_text,
            context_text,
            clean_text(job.get("job_search_text", "")),
            clean_text(job.get("job_description", "")),
        ]
    )
    return contains_any(searchable_text, INDIA_LOCATION_WORDS)


def build_location_text(job: dict) -> str:
    return " ".join(
        [
            clean_text(job.get("job_city", "")),
            clean_text(job.get("job_state", "")),
            clean_text(job.get("job_country", "")),
            clean_text(job.get("job_location", "")),
        ]
    )


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
