import os
from pathlib import Path

from dotenv import load_dotenv
import yaml


PROJECT_ROOT = Path(
    os.getenv("JOB_CURATOR_PROJECT_ROOT", Path(__file__).resolve().parents[2])
).resolve()


def load_settings() -> dict:
    dotenv_path = os.getenv("JOB_CURATOR_ENV_FILE", str(PROJECT_ROOT / ".env"))
    load_dotenv(dotenv_path)

    config_path = Path(
        os.getenv("JOB_CURATOR_CONFIG_FILE", str(PROJECT_ROOT / "config" / "config.yaml"))
    )
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    api_key = os.getenv("JSEARCH_API_KEY")
    api_host = os.getenv("JSEARCH_API_HOST", "jsearch.p.rapidapi.com")
    source = config.get("search", {}).get("source", "linkedin")

    if not api_key and source != "linkedin":
        raise RuntimeError("Missing JSEARCH_API_KEY. Add it to your .env file.")

    config["api"]["key"] = api_key or ""
    config["api"]["host"] = api_host
    apply_runtime_overrides(config)
    return config


def apply_runtime_overrides(config: dict) -> None:
    search_config = config.setdefault("search", {})
    output_config = config.setdefault("output", {})
    operational_config = config.setdefault("operational", {})
    email_config = config.setdefault("email", {})
    dashboard_upload_config = config.setdefault("dashboard_upload", {})

    apply_env_override(output_config, "raw_dir", "JOB_CURATOR_OUTPUT_DIR")
    apply_env_override(operational_config, "state_dir", "JOB_CURATOR_STATE_DIR")
    apply_env_override(operational_config, "log_dir", "JOB_CURATOR_LOG_DIR")
    apply_env_override(operational_config, "seed_state_dir", "JOB_CURATOR_SEED_STATE_DIR")
    apply_env_override(
        operational_config,
        "recent_job_window_days",
        "JOB_CURATOR_RECENT_JOB_WINDOW_DAYS",
        cast=int,
    )
    apply_env_override(
        operational_config,
        "seen_retention_days",
        "JOB_CURATOR_SEEN_RETENTION_DAYS",
        cast=int,
    )
    apply_env_override(
        search_config,
        "headless",
        "JOB_CURATOR_HEADLESS",
        cast=parse_bool,
    )
    apply_env_override(
        email_config,
        "enabled",
        "JOB_CURATOR_EMAIL_ENABLED",
        cast=parse_bool,
    )
    apply_env_override(
        dashboard_upload_config,
        "enabled",
        "DASHBOARD_UPLOAD_ENABLED",
        cast=parse_bool,
    )
    apply_env_override(dashboard_upload_config, "api_url", "DASHBOARD_API_URL")
    apply_env_override(dashboard_upload_config, "auth_token", "DASHBOARD_AUTH_TOKEN")
    apply_env_override(dashboard_upload_config, "guid", "DASHBOARD_GUID")
    apply_env_override(dashboard_upload_config, "x_auth_key", "DASHBOARD_X_AUTH_KEY")
    apply_env_override(
        dashboard_upload_config,
        "max_jobs_per_vertical",
        "DASHBOARD_MAX_JOBS_PER_VERTICAL",
        cast=int,
    )


def apply_env_override(
    config: dict,
    key: str,
    env_name: str,
    cast=None,
) -> None:
    value = os.getenv(env_name)
    if value is None or value == "":
        return

    config[key] = cast(value) if cast else value


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
