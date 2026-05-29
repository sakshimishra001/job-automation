import hashlib
import logging
import re
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

LOCATION_TOKEN_DROP_WORDS = {
    "india",
    "remote",
    "hybrid",
    "onsite",
    "on-site",
}


def deduplicate_jobs(jobs: list[dict]) -> list[dict]:
    seen_keys = set()
    unique_jobs = []

    for job in jobs:
        keys = build_dedupe_keys(job)
        if any(key in seen_keys for key in keys):
            continue

        seen_keys.update(keys)
        unique_jobs.append(job)

    logger.info("Removed %s duplicate jobs", len(jobs) - len(unique_jobs))
    return unique_jobs


def build_dedupe_keys(job: dict) -> list[str]:
    keys = []

    canonical_url = build_canonical_url_key(job)
    if canonical_url:
        keys.append(f"url:{canonical_url}")

    source_job_id = extract_source_job_id(job.get("job_apply_link", ""))
    if source_job_id:
        keys.append(f"id:{source_job_id}")

    fingerprint = build_fingerprint(job)
    if fingerprint:
        keys.append(f"fp:{fingerprint}")

    relaxed_fingerprint = build_relaxed_fingerprint(job)
    if relaxed_fingerprint:
        keys.append(f"rfp:{relaxed_fingerprint}")

    return keys


def build_seen_record(job: dict, fetched_date: str) -> dict:
    return {
        "apply_link": normalize_url(job.get("job_apply_link", "")),
        "title": normalize_text(job.get("job_title", "")),
        "company": normalize_text(job.get("employer_name", "")),
        "location": normalize_location(job.get("job_city", "") or job.get("job_location", "")),
        "fingerprint": build_fingerprint(job),
        "relaxed_fingerprint": build_relaxed_fingerprint(job),
        "canonical_url_key": build_canonical_url_key(job),
        "source_job_id": extract_source_job_id(job.get("job_apply_link", "")),
        "fetched_date": fetched_date,
    }


def build_dedupe_keys_from_seen_record(record: dict) -> list[str]:
    keys = []

    canonical_url = clean_text(record.get("canonical_url_key", "")) or build_canonical_url_key(
        {"job_apply_link": record.get("apply_link", "")}
    )
    if canonical_url:
        keys.append(f"url:{canonical_url}")

    source_job_id = clean_text(record.get("source_job_id", "")) or extract_source_job_id(
        record.get("apply_link", "")
    )
    if source_job_id:
        keys.append(f"id:{source_job_id}")

    fingerprint = clean_text(record.get("fingerprint", ""))
    if not fingerprint:
        fingerprint = build_hash(
            [
                normalize_text(record.get("title", "")),
                normalize_text(record.get("company", "")),
                normalize_location(record.get("location", "")),
            ]
        )
    if fingerprint:
        keys.append(f"fp:{fingerprint}")

    relaxed_fingerprint = clean_text(record.get("relaxed_fingerprint", ""))
    if not relaxed_fingerprint:
        relaxed_fingerprint = build_hash(
            [
                normalize_text(record.get("title", "")),
                normalize_text(record.get("company", "")),
            ]
        )
    if relaxed_fingerprint:
        keys.append(f"rfp:{relaxed_fingerprint}")

    return keys


def build_fingerprint(job: dict) -> str:
    return build_hash(
        [
            normalize_text(job.get("job_title", "")),
            normalize_text(job.get("employer_name", "")),
            normalize_location(job.get("job_city", "") or job.get("job_location", "")),
        ]
    )


def build_relaxed_fingerprint(job: dict) -> str:
    return build_hash(
        [
            normalize_text(job.get("job_title", "")),
            normalize_text(job.get("employer_name", "")),
        ]
    )


def build_canonical_url_key(job: dict) -> str:
    url = normalize_url(job.get("company_apply_url") or job.get("job_apply_link", ""))
    if not url:
        return ""

    source_job_id = extract_source_job_id(url)
    if source_job_id:
        return source_job_id

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    path = re.sub(r"/+", "/", parsed.path.rstrip("/").lower())
    return f"{host}{path}"


def extract_source_job_id(url: object) -> str:
    text = normalize_url(url)
    if not text:
        return ""

    parsed = urlparse(text)
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.lower()

    linkedin_match = re.search(r"/jobs/view/(?:[^/]+-)?(\d+)", path)
    if linkedin_match:
        return f"linkedin:{linkedin_match.group(1)}"

    generic_numeric_match = re.search(r"-(\d{6,})$", path.rstrip("/"))
    if generic_numeric_match:
        return f"{host}:{generic_numeric_match.group(1)}"

    return ""


def normalize_text(value: object) -> str:
    text = clean_text(value)
    text = re.sub(r"\b(sr|sr\.|mgr|vp)\b", expand_short_token, text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_location(value: object) -> str:
    text = normalize_text(value)
    tokens = [token for token in text.split() if token not in LOCATION_TOKEN_DROP_WORDS]
    return " ".join(tokens)


def normalize_url(value: object) -> str:
    text = clean_text(value)
    if not text:
        return ""

    text = text.split("#")[0].split("?")[0]
    return text.rstrip("/")


def build_hash(parts: list[str]) -> str:
    normalized_parts = [part for part in parts if part]
    if not normalized_parts:
        return ""

    joined = "|".join(normalized_parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def expand_short_token(match: re.Match) -> str:
    token = match.group(1)
    mapping = {
        "sr": "senior",
        "sr.": "senior",
        "mgr": "manager",
        "vp": "vice president",
    }
    return mapping.get(token, token)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
