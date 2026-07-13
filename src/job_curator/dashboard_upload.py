import logging
from dataclasses import dataclass

import requests

from src.job_curator.export_csv import preferred_apply_link


logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_MAP = {
    "Product Management": "PM",
    "Project Management": "PMT",
    "Data Science": "DS",
    "Finance": "FT",
    "HR": "HR",
    "Cybersecurity": "CS",
}

LEVEL_MAP = {
    "junior": "Junior",
    "mid": "Mid",
    "senior": "Senior",
    "executive": "Senior",
}


@dataclass
class DashboardUploadResult:
    vertical: str
    attempted: int = 0
    uploaded: int = 0
    failed: int = 0
    skipped: int = 0


def upload_dashboard_jobs(
    jobs: list[dict],
    vertical: str,
    upload_config: dict,
) -> DashboardUploadResult:
    result = DashboardUploadResult(vertical=vertical)

    if not upload_config.get("enabled", False):
        return result

    category_map = upload_config.get("category_map") or DEFAULT_CATEGORY_MAP
    category = category_map.get(vertical)
    if not category:
        result.skipped = len(jobs)
        logger.info("Skipping dashboard upload for unmapped vertical: %s", vertical)
        return result

    settings = load_dashboard_upload_settings(upload_config)
    if not settings:
        result.skipped = len(jobs)
        logger.warning("Dashboard upload is enabled but API settings are incomplete")
        return result

    max_jobs = int(upload_config.get("max_jobs_per_vertical", 1))
    selected_jobs = jobs[:max_jobs]
    result.attempted = len(selected_jobs)

    for job in selected_jobs:
        if upload_single_dashboard_job(job, category, settings):
            result.uploaded += 1
        else:
            result.failed += 1

    logger.info(
        "Dashboard upload summary for %s: attempted=%s uploaded=%s failed=%s skipped=%s",
        vertical,
        result.attempted,
        result.uploaded,
        result.failed,
        result.skipped,
    )
    return result


def load_dashboard_upload_settings(upload_config: dict) -> dict:
    settings = {
        "api_url": str(upload_config.get("api_url", "")).strip(),
        "auth_token": str(upload_config.get("auth_token", "")).strip(),
        "guid": str(upload_config.get("guid", "")).strip(),
        "x_auth_key": str(upload_config.get("x_auth_key", "")).strip(),
        "timeout_seconds": int(upload_config.get("timeout_seconds", 30)),
    }

    required = ["api_url", "auth_token", "guid", "x_auth_key"]
    missing = [field for field in required if not settings[field]]
    if missing:
        logger.warning("Missing dashboard upload settings fields: %s", ", ".join(missing))
        return {}

    return settings


def upload_single_dashboard_job(job: dict, category: str, settings: dict) -> bool:
    payload = build_dashboard_payload(job, category)
    if not all(payload.values()):
        logger.warning("Skipping dashboard upload because required job fields are missing: %s", payload)
        return False

    headers = {
        "Authorization": build_authorization_header(settings["auth_token"]),
        "guid": settings["guid"],
        "x-auth-key": settings["x_auth_key"],
    }

    try:
        response = requests.post(
            settings["api_url"],
            headers=headers,
            data=payload,
            timeout=settings["timeout_seconds"],
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning(
            "Dashboard upload failed for %s at %s: %s",
            payload.get("jobtitle"),
            payload.get("company_name"),
            error,
        )
        return False

    logger.info(
        "Uploaded dashboard job: title=%s company=%s category=%s",
        payload["jobtitle"],
        payload["company_name"],
        payload["category"],
    )
    return True


def build_dashboard_payload(job: dict, category: str) -> dict:
    return {
        "company_name": str(job.get("employer_name", "")).strip(),
        "job_link": preferred_apply_link(job).strip(),
        "jobtitle": str(job.get("job_title", "")).strip(),
        "level": map_dashboard_level(job),
        "category": category,
    }


def map_dashboard_level(job: dict) -> str:
    bucket = str(job.get("experience_bucket") or job.get("seniority_level") or "").strip().lower()
    return LEVEL_MAP.get(bucket, "Mid")


def build_authorization_header(token: str) -> str:
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"
