import logging
import os
import smtplib
from email.message import EmailMessage

from src.job_curator.operational_state import format_datetime


logger = logging.getLogger(__name__)


def send_run_summary_email(
    summary: dict,
    email_config: dict,
) -> None:
    if not email_config.get("enabled", False):
        return

    settings = load_email_settings(email_config)
    if not settings:
        logger.warning("Email summary is enabled but SMTP settings are incomplete")
        return

    message = EmailMessage()
    message["Subject"] = email_config.get("subject", "Job curator run summary")
    message["From"] = settings["from_address"]
    message["To"] = settings["to_address"]
    message.set_content(build_email_body(summary))

    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=30) as server:
            server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(message)
    except OSError as error:
        logger.warning("Could not send email summary: %s", error)
        return

    logger.info("Sent email summary to %s", settings["to_address"])


def load_email_settings(email_config: dict) -> dict:
    port_value = os.getenv("SMTP_PORT", str(email_config.get("smtp_port", 587))).strip()
    if not port_value:
        port_value = str(email_config.get("smtp_port", 587))

    try:
        port = int(port_value)
    except ValueError:
        logger.warning("SMTP_PORT is invalid: %s", port_value)
        return {}

    settings = {
        "host": os.getenv("SMTP_HOST", email_config.get("smtp_host", "")).strip(),
        "port": port,
        "username": os.getenv("SMTP_USERNAME", email_config.get("smtp_username", "")).strip(),
        "password": os.getenv("SMTP_PASSWORD", email_config.get("smtp_password", "")).strip(),
        "from_address": os.getenv("EMAIL_FROM", email_config.get("from", "")).strip(),
        "to_address": os.getenv("EMAIL_TO", email_config.get("to", "")).strip(),
    }

    required = ["host", "username", "password", "from_address", "to_address"]
    if any(not settings[field] for field in required):
        return {}

    return settings


def build_email_body(summary: dict) -> str:
    lines = [
        "Job curator run summary",
        "",
        f"Started: {format_datetime(summary['started_at'])}",
        f"Finished: {format_datetime(summary['finished_at'])}",
        f"Runtime seconds: {summary['runtime_seconds']}",
        f"Total fetched: {summary['total_fetched']}",
        f"Total exported new jobs: {summary['total_exported']}",
        f"Failed verticals: {', '.join(summary['failed_verticals']) or 'None'}",
        "",
        "Vertical counts:",
    ]

    for vertical in summary["verticals"]:
        lines.append(
            "- {name}: fetched={fetched}, fresh={fresh}, exported={exported}, "
            "seen_skipped={seen_skipped}, stale_skipped={stale_skipped}".format(
                name=vertical["name"],
                fetched=vertical["fetched"],
                fresh=vertical["fresh"],
                exported=vertical["exported"],
                seen_skipped=vertical["seen_skipped"],
                stale_skipped=vertical["stale_skipped"],
            )
        )

    return "\n".join(lines)
