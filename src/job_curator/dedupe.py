import logging


logger = logging.getLogger(__name__)


def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    seen_keys = set()
    unique_jobs = []

    for job in jobs:
        key = build_dedupe_key(job)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_jobs.append(job)

    logger.info("Removed %s duplicate jobs", len(jobs) - len(unique_jobs))
    return unique_jobs


def build_dedupe_key(job: dict) -> str:
    apply_link = clean_text(job.get("job_apply_link", ""))
    if apply_link:
        return apply_link

    return "|".join(
        [
            clean_text(job.get("job_title", "")),
            clean_text(job.get("employer_name", "")),
            clean_text(job.get("job_city", "")),
        ]
    )


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
