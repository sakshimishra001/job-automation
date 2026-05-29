import csv
import logging
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "job_title",
    "employer_name",
    "city",
    "employment_type",
    "seniority_level",
    "experience_bucket",
    "location_scope",
    "vertical",
    "posted_date",
    "apply_link",
    "publisher",
]


def export_jobs_to_csv(jobs: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"raw_jobs_{file_timestamp}.csv"

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for job in jobs:
            writer.writerow(
                {
                    "job_title": job.get("job_title", ""),
                    "employer_name": job.get("employer_name", ""),
                    "city": job.get("job_city", ""),
                    "employment_type": job.get("job_employment_type", ""),
                    "seniority_level": job.get("seniority_level", ""),
                    "experience_bucket": job.get("experience_bucket", ""),
                    "location_scope": job.get("location_scope", ""),
                    "vertical": job.get("vertical", ""),
                    "posted_date": job.get("job_posted_at_datetime_utc", ""),
                    "apply_link": preferred_apply_link(job),
                    "publisher": job.get("job_publisher", ""),
                }
            )

    return output_path


def export_vertical_jobs_to_csv(
    jobs: list[dict],
    output_dir: Path,
    vertical: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slugify(vertical)}.csv"

    try:
        write_jobs_csv(jobs, output_path)
        return output_path
    except PermissionError:
        fallback_path = build_fallback_output_path(output_dir, vertical)
        logger.warning(
            "Could not write %s because it is locked or permission was denied. "
            "Writing fallback CSV to %s",
            output_path,
            fallback_path,
        )
        write_jobs_csv(jobs, fallback_path)
        return fallback_path


def write_jobs_csv(jobs: list[dict], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for job in jobs:
            writer.writerow(
                {
                    "job_title": job.get("job_title", ""),
                    "employer_name": job.get("employer_name", ""),
                    "city": job.get("job_city", ""),
                    "employment_type": job.get("job_employment_type", ""),
                    "seniority_level": job.get("seniority_level", ""),
                    "experience_bucket": job.get("experience_bucket", ""),
                    "location_scope": job.get("location_scope", ""),
                    "vertical": job.get("vertical", ""),
                    "posted_date": job.get("job_posted_at_datetime_utc", ""),
                    "apply_link": preferred_apply_link(job),
                    "publisher": job.get("job_publisher", ""),
                }
            )


def slugify(value: str) -> str:
    return (
        value.lower()
        .replace(" / ", "_")
        .replace("/", "_")
        .replace(" & ", "_")
        .replace("&", "_")
        .replace(" ", "_")
    )


def build_fallback_output_path(output_dir: Path, vertical: str) -> Path:
    file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"{slugify(vertical)}_{file_timestamp}.csv"


def preferred_apply_link(job: dict) -> str:
    return job.get("company_apply_url") or job.get("job_apply_link", "")
