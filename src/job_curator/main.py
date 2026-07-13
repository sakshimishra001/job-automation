import logging
from pathlib import Path

from src.job_curator.classify import (
    classify_seniority_for_jobs,
    select_jobs_by_experience_bucket,
    set_vertical_for_jobs,
    validate_jobs_for_vertical,
)
from src.job_curator.dashboard_upload import upload_dashboard_jobs
from src.job_curator.dedupe import deduplicate_jobs
from src.job_curator.email_summary import send_run_summary_email
from src.job_curator.export_csv import export_vertical_jobs_to_csv
from src.job_curator.fetch_jobs import (
    RateLimitError,
    build_vertical_queries,
    fetch_jobs_for_queries,
)
from src.job_curator.filters import (
    annotate_location_scope_for_jobs,
    keep_approved_publishers,
    keep_supported_location_scope_jobs,
)
from src.job_curator.operational_state import (
    keep_fresh_jobs_by_bucket,
    load_run_state,
    load_seen_jobs,
    save_run_state,
    save_seen_jobs,
    seed_state_files,
    skip_recently_seen_jobs,
    update_seen_jobs,
    utc_now,
)
from src.job_curator.settings import PROJECT_ROOT, load_settings


def setup_logging(log_dir: Path | None = None) -> None:
    handlers = [logging.StreamHandler()]

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "job_curator.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Starting job fetch")
    config = load_settings()

    raw_dir = Path(config["output"]["raw_dir"])
    output_dir = PROJECT_ROOT / raw_dir
    search_config = config["search"]
    operational_config = config.get("operational", {})
    state_dir = PROJECT_ROOT / Path(operational_config.get("state_dir", "data/state"))
    log_dir = PROJECT_ROOT / Path(operational_config.get("log_dir", "data/logs"))
    seed_state_dir_value = operational_config.get("seed_state_dir")
    seed_state_dir = (
        Path(seed_state_dir_value)
        if seed_state_dir_value
        else None
    )
    setup_logging(log_dir)
    logger = logging.getLogger(__name__)

    run_state_path = state_dir / operational_config.get("run_state_file", "run_state.json")
    seen_jobs_path = state_dir / operational_config.get("seen_jobs_file", "seen_jobs.csv")
    recent_job_window_days = int(operational_config.get("recent_job_window_days", 7))
    seen_retention_days = int(operational_config.get("seen_retention_days", 14))
    curation_config = config.get("curation", {})
    dashboard_upload_config = config.get("dashboard_upload", {})
    bucket_quotas = curation_config.get(
        "experience_bucket_quotas",
        {"Junior": 2, "Mid": 4, "Senior": 5, "Executive": 4},
    )
    vertical_validation_min_score = int(curation_config.get("vertical_validation_min_score", 1))
    freshness_windows_by_bucket = curation_config.get(
        "freshness_window_days_by_bucket",
        {"Junior": 3, "Mid": 7, "Senior": 14, "Executive": 30},
    )

    run_started_at = utc_now()
    seed_state_files(
        state_dir,
        seed_state_dir,
        [run_state_path.name, seen_jobs_path.name, seen_jobs_path.with_suffix(".json").name],
    )
    load_run_state(run_state_path)
    seen_jobs = load_seen_jobs(seen_jobs_path)
    logger.info(
        "Keeping jobs using dynamic freshness windows by bucket: %s",
        freshness_windows_by_bucket,
    )

    verticals = search_config["role_queries"].keys()
    quota = int(search_config.get("quota_per_vertical", 15))
    minimum_jobs = int(search_config.get("minimum_jobs_per_vertical", 10))
    exported_jobs = []
    failed_verticals = []
    vertical_summaries = []
    export_files = []

    for vertical in verticals:
        logger.info("Starting vertical: %s", vertical)

        queries = build_vertical_queries(search_config, vertical)
        try:
            jobs = fetch_jobs_for_queries(config["api"], search_config, queries)
        except RateLimitError as error:
            logger.error("%s", error)
            logger.error("Stopping run early so the API is not called again.")
            failed_verticals.append(vertical)
            break

        fetched_count = len(jobs)
        jobs = keep_approved_publishers(jobs)
        jobs = classify_seniority_for_jobs(jobs)
        jobs = keep_fresh_jobs_by_bucket(
            jobs,
            run_started_at,
            freshness_windows_by_bucket,
            recent_job_window_days,
        )
        fresh_count = len(jobs)
        jobs = annotate_location_scope_for_jobs(jobs)
        jobs = keep_supported_location_scope_jobs(jobs)
        jobs = validate_jobs_for_vertical(jobs, vertical, min_score=vertical_validation_min_score)
        jobs = keep_supported_experience_jobs(jobs)
        jobs = set_vertical_for_jobs(jobs, vertical)
        jobs = deduplicate_jobs(jobs)
        before_seen_count = len(jobs)
        jobs = skip_recently_seen_jobs(
            jobs,
            seen_jobs,
            seen_retention_days,
            run_started_at,
        )
        after_seen_count = len(jobs)
        jobs = select_jobs_for_vertical_quota(
            jobs,
            quota,
            bucket_quotas,
        )
        exported_jobs.extend(jobs)
        seen_jobs = update_seen_jobs(
            seen_jobs,
            jobs,
            seen_retention_days,
            run_started_at,
        )
        exported_count = len(jobs)
        stale_skipped = fetched_count - fresh_count
        seen_skipped = before_seen_count - after_seen_count
        vertical_summaries.append(
            {
                "name": vertical,
                "fetched": fetched_count,
                "fresh": fresh_count,
                "stale_skipped": stale_skipped,
                "seen_skipped": seen_skipped,
                "exported": exported_count,
            }
        )

        if len(jobs) < minimum_jobs:
            logger.warning(
                "%s produced only %s jobs; target is %s-%s",
                vertical,
                len(jobs),
                minimum_jobs,
                quota,
            )

        output_path = export_vertical_jobs_to_csv(jobs, output_dir, vertical)
        export_files.append(str(output_path))
        logger.info("Saved %s %s jobs to %s", len(jobs), vertical, output_path)
        upload_dashboard_jobs(jobs, vertical, dashboard_upload_config)
        logger.info(
            "Summary for %s: fetched=%s fresh=%s stale_skipped=%s seen_skipped=%s exported=%s",
            vertical,
            fetched_count,
            fresh_count,
            stale_skipped,
            seen_skipped,
            exported_count,
        )

    if failed_verticals:
        logger.error(
            "Run finished with failed verticals; not updating operational state: %s",
            ", ".join(failed_verticals),
        )
    else:
        seen_jobs = update_seen_jobs(
            seen_jobs,
            exported_jobs,
            seen_retention_days,
            run_started_at,
        )
        save_seen_jobs(seen_jobs_path, seen_jobs)
        save_run_state(run_state_path, run_started_at)
        logger.info("Updated operational state after successful run")

    run_finished_at = utc_now()
    summary = {
        "started_at": run_started_at,
        "finished_at": run_finished_at,
        "runtime_seconds": round((run_finished_at - run_started_at).total_seconds(), 2),
        "total_fetched": sum(item["fetched"] for item in vertical_summaries),
        "total_exported": len(exported_jobs),
        "failed_verticals": failed_verticals,
        "verticals": vertical_summaries,
        "exported_jobs_today": exported_jobs,
        "export_files": export_files,
        "run_state_path": str(run_state_path),
    }
    log_run_summary(summary)
    send_run_summary_email(summary, config.get("email", {}))

    logger.info("Finished")


def keep_supported_experience_jobs(jobs: list[dict]) -> list[dict]:
    kept_jobs = [
        job
        for job in jobs
        if str(job.get("experience_bucket", "")).strip().lower()
        in {"junior", "mid", "senior", "executive"}
    ]
    logging.getLogger(__name__).info(
        "Kept %s jobs with supported experience buckets and rejected %s unsupported jobs",
        len(kept_jobs),
        len(jobs) - len(kept_jobs),
    )
    return kept_jobs


def select_jobs_for_vertical_quota(
    jobs: list[dict],
    total_quota: int,
    bucket_quotas: dict[str, int],
) -> list[dict]:
    if total_quota <= 0 or not jobs:
        return []
    india_jobs = [job for job in jobs if job.get("location_scope") == "India"]
    return select_jobs_by_experience_bucket(india_jobs, total_quota, bucket_quotas)[:total_quota]


def log_run_summary(summary: dict) -> None:
    logger = logging.getLogger(__name__)
    logger.info(
        "Run summary: fetched=%s exported=%s failed_verticals=%s runtime_seconds=%s",
        summary["total_fetched"],
        summary["total_exported"],
        ", ".join(summary["failed_verticals"]) or "None",
        summary["runtime_seconds"],
    )

    for vertical in summary["verticals"]:
        logger.info(
            "Run summary vertical=%s fetched=%s fresh=%s stale_skipped=%s "
            "seen_skipped=%s exported=%s",
            vertical["name"],
            vertical["fetched"],
            vertical["fresh"],
            vertical["stale_skipped"],
            vertical["seen_skipped"],
            vertical["exported"],
        )


if __name__ == "__main__":
    main()
