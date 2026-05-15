import csv
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seed_state_files(
    target_dir: Path,
    seed_dir: Path | None,
    filenames: list[str],
) -> None:
    if seed_dir is None or not seed_dir.exists():
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    for filename in filenames:
        target_path = target_dir / filename
        seed_path = seed_dir / filename
        if target_path.exists() or not seed_path.exists():
            continue

        try:
            shutil.copy2(seed_path, target_path)
            logger.info("Seeded state file from %s to %s", seed_path, target_path)
        except OSError as error:
            logger.warning("Could not seed state file %s: %s", seed_path, error)


def load_run_state(path: Path) -> dict:
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        logger.warning("Could not read run state from %s: %s", path, error)
        return {}


def save_run_state(path: Path, run_time: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"last_successful_run": format_datetime(run_time)}

    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2)


def get_last_successful_run(state: dict) -> datetime | None:
    return parse_datetime(state.get("last_successful_run"))


def build_freshness_cutoff(
    last_successful_run: datetime | None,
    overlap_buffer_hours: float,
) -> datetime | None:
    if last_successful_run is None:
        return None

    return last_successful_run - timedelta(hours=overlap_buffer_hours)


def build_recent_jobs_cutoff(run_time: datetime, recent_job_window_days: int) -> datetime:
    return run_time - timedelta(days=recent_job_window_days)


def keep_fresh_jobs(jobs: list[dict], cutoff: datetime | None) -> list[dict]:
    if cutoff is None:
        logger.info("No previous successful run found; keeping all fetched jobs")
        return jobs

    kept_jobs = []
    skipped_jobs = 0

    for job in jobs:
        job_time = get_job_freshness_time(job)
        if job_time is None or job_time >= cutoff:
            kept_jobs.append(job)
        else:
            skipped_jobs += 1

    logger.info(
        "Kept %s fresh jobs and skipped %s stale jobs using cutoff %s",
        len(kept_jobs),
        skipped_jobs,
        format_datetime(cutoff),
    )
    return kept_jobs


def get_job_freshness_time(job: dict) -> datetime | None:
    return parse_datetime(job.get("job_posted_at_datetime_utc")) or parse_datetime(
        job.get("fetched_at")
    )


def load_seen_jobs(path: Path) -> list[dict]:
    if not path.exists():
        legacy_path = path.with_suffix(".json")
        if legacy_path.exists():
            logger.info("Loading legacy seen jobs from %s", legacy_path)
            return load_seen_jobs_json(legacy_path)
        return []

    try:
        if path.suffix.lower() == ".json":
            return load_seen_jobs_json(path)

        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            return [
                {
                    "apply_link": row.get("apply_link", ""),
                    "title": row.get("title", ""),
                    "company": row.get("company", ""),
                    "fetched_date": row.get("fetched_date", ""),
                }
                for row in reader
            ]
    except OSError as error:
        logger.warning("Could not read seen jobs from %s: %s", path, error)
        return []


def load_seen_jobs_json(path: Path) -> list[dict]:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        logger.warning("Could not read seen jobs from %s: %s", path, error)
        return []

    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        return []

    return jobs


def save_seen_jobs(path: Path, seen_jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["apply_link", "title", "company", "fetched_date"],
        )
        writer.writeheader()
        writer.writerows(seen_jobs)


def skip_recently_seen_jobs(
    jobs: list[dict],
    seen_jobs: list[dict],
    retention_days: int,
    run_time: datetime,
) -> list[dict]:
    recent_keys = build_recent_seen_keys(seen_jobs, retention_days, run_time)
    kept_jobs = []
    skipped_jobs = 0

    for job in jobs:
        key = build_seen_key_from_job(job)
        if key and key in recent_keys:
            skipped_jobs += 1
            continue

        kept_jobs.append(job)

    logger.info("Skipped %s jobs seen in the last %s days", skipped_jobs, retention_days)
    return kept_jobs


def update_seen_jobs(
    seen_jobs: list[dict],
    jobs: list[dict],
    retention_days: int,
    run_time: datetime,
) -> list[dict]:
    retained_jobs = prune_seen_jobs(seen_jobs, retention_days, run_time)
    existing_keys = {
        build_seen_key_from_seen_job(job)
        for job in retained_jobs
        if build_seen_key_from_seen_job(job)
    }

    for job in jobs:
        key = build_seen_key_from_job(job)
        if not key or key in existing_keys:
            continue

        retained_jobs.append(
            {
                "apply_link": clean_text(job.get("job_apply_link", "")),
                "title": clean_text(job.get("job_title", "")),
                "company": clean_text(job.get("employer_name", "")),
                "fetched_date": format_datetime(run_time),
            }
        )
        existing_keys.add(key)

    return retained_jobs


def prune_seen_jobs(
    seen_jobs: list[dict],
    retention_days: int,
    run_time: datetime,
) -> list[dict]:
    cutoff = run_time - timedelta(days=retention_days)
    retained_jobs = []

    for job in seen_jobs:
        fetched_date = parse_datetime(job.get("fetched_date"))
        if fetched_date is None or fetched_date >= cutoff:
            retained_jobs.append(job)

    return retained_jobs


def build_recent_seen_keys(
    seen_jobs: list[dict],
    retention_days: int,
    run_time: datetime,
) -> set[str]:
    recent_jobs = prune_seen_jobs(seen_jobs, retention_days, run_time)
    return {
        build_seen_key_from_seen_job(job)
        for job in recent_jobs
        if build_seen_key_from_seen_job(job)
    }


def build_seen_key_from_job(job: dict) -> str:
    apply_link = clean_text(job.get("job_apply_link", ""))
    if apply_link:
        return apply_link

    return "|".join(
        [
            clean_text(job.get("job_title", "")),
            clean_text(job.get("employer_name", "")),
        ]
    )


def build_seen_key_from_seen_job(job: dict) -> str:
    apply_link = clean_text(job.get("apply_link", ""))
    if apply_link:
        return apply_link

    return "|".join(
        [
            clean_text(job.get("title", "")),
            clean_text(job.get("company", "")),
        ]
    )


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
