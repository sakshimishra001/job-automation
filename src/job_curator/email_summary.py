import json
import logging
import os
import smtplib
import zipfile
from datetime import date, timedelta, timezone
from email.message import EmailMessage
from html import escape
from pathlib import Path

from src.job_curator.operational_state import parse_datetime


logger = logging.getLogger(__name__)

LOCAL_TZ = timezone(timedelta(hours=5, minutes=30))
REPORTING_STATE_KEY = "email_reporting"
REPORTING_HISTORY_DAYS = 21
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

    report = build_business_report(summary)

    message = EmailMessage()
    message["Subject"] = build_email_subject(summary)
    message["From"] = settings["from_address"]
    message["To"] = settings["to_address"]
    report["attachment_note"] = describe_export_attachment(summary)
    message.set_content(build_plain_text_body(report))
    message.add_alternative(build_html_body(report), subtype="html")
    attach_export_package(message, summary)

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
    missing_fields = [field for field in required if not settings[field]]
    if missing_fields:
        logger.warning(
            "Missing email settings fields: %s",
            ", ".join(missing_fields),
        )
        return {}

    return settings


def build_business_report(summary: dict) -> dict:
    execution_dt_local = summary["started_at"].astimezone(LOCAL_TZ)
    execution_date = execution_dt_local.date()
    run_state_path = Path(summary.get("run_state_path", "")).expanduser()
    today_counts = {
        item["name"]: int(item.get("exported", 0) or 0)
        for item in summary.get("verticals", [])
    }
    vertical_order = list(today_counts.keys())

    existing_state = load_reporting_state(run_state_path)
    existing_history = prune_history(existing_state.get("history", []), execution_date)
    today_entry = build_reporting_entry(summary, execution_date)

    effective_history = replace_or_append_entry(existing_history, today_entry)
    weekly_entries = filter_entries_for_week(effective_history, execution_date)
    weekly_counts = aggregate_weekly_counts(weekly_entries, vertical_order)

    if not summary.get("failed_verticals"):
        save_reporting_state(run_state_path, existing_state, effective_history)

    return {
        "execution_date": execution_date,
        "vertical_order": vertical_order,
        "today_counts": today_counts,
        "today_total": sum(today_counts.values()),
        "weekly_counts": weekly_counts,
        "weekly_total": sum(weekly_counts.values()),
        "failed_verticals": summary.get("failed_verticals", []),
        "attachment_note": "No export attachments were added.",
    }


def build_reporting_entry(summary: dict, execution_date: date) -> dict:
    jobs = []
    for job in summary.get("exported_jobs_today", []):
        jobs.append(
            {
                "vertical": str(job.get("vertical", "")).strip(),
                "job_title": str(job.get("job_title", "")).strip(),
                "apply_link": str(job.get("job_apply_link", "")).strip(),
                "company_apply_url": str(job.get("company_apply_url", "")).strip(),
                "publisher": str(job.get("job_publisher", "")).strip(),
            }
        )

    return {
        "run_date": execution_date.isoformat(),
        "vertical_counts": {
            item["name"]: int(item.get("exported", 0) or 0)
            for item in summary.get("verticals", [])
        },
        "jobs": jobs,
    }


def load_reporting_state(run_state_path: Path) -> dict:
    if not run_state_path.exists():
        return {}

    try:
        with run_state_path.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not read reporting state from %s: %s", run_state_path, error)
        return {}

    return state.get(REPORTING_STATE_KEY, {})


def save_reporting_state(run_state_path: Path, existing_reporting_state: dict, history: list[dict]) -> None:
    state_payload = {}
    if run_state_path.exists():
        try:
            with run_state_path.open("r", encoding="utf-8") as file:
                state_payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            state_payload = {}

    reporting_state = dict(existing_reporting_state)
    reporting_state["history"] = history
    state_payload[REPORTING_STATE_KEY] = reporting_state

    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    with run_state_path.open("w", encoding="utf-8") as file:
        json.dump(state_payload, file, indent=2)


def prune_history(history: list[dict], execution_date: date) -> list[dict]:
    cutoff = execution_date - timedelta(days=REPORTING_HISTORY_DAYS)
    pruned = []

    for entry in history:
        run_date = parse_history_date(entry.get("run_date"))
        if run_date is None or run_date < cutoff:
            continue
        pruned.append(entry)

    return pruned


def replace_or_append_entry(history: list[dict], new_entry: dict) -> list[dict]:
    updated = [entry for entry in history if entry.get("run_date") != new_entry.get("run_date")]
    updated.append(new_entry)
    return sorted(updated, key=lambda entry: entry.get("run_date", ""))


def filter_entries_for_week(history: list[dict], execution_date: date) -> list[dict]:
    week_start = execution_date - timedelta(days=execution_date.weekday())
    weekly_entries = []

    for entry in history:
        run_date = parse_history_date(entry.get("run_date"))
        if run_date is None:
            continue
        if week_start <= run_date <= execution_date:
            weekly_entries.append(entry)

    return weekly_entries


def aggregate_weekly_counts(history: list[dict], vertical_order: list[str]) -> dict[str, int]:
    counts = {vertical: 0 for vertical in vertical_order}

    for entry in history:
        for vertical, count in entry.get("vertical_counts", {}).items():
            counts.setdefault(vertical, 0)
            counts[vertical] += int(count or 0)

    return counts


def build_email_subject(summary: dict) -> str:
    execution_date = summary["started_at"].astimezone(LOCAL_TZ).strftime("%d %b %Y")
    return f"Job Listings Summary - {execution_date}"


def build_plain_text_body(report: dict) -> str:
    lines = [
        f"Job Listings Summary - {report['execution_date'].strftime('%d %b %Y')}",
        "",
        "Export Summary",
    ]

    for vertical in report["vertical_order"]:
        lines.append(
            "- {vertical}: exported today={today}, total exported till date={weekly}".format(
                vertical=vertical,
                today=report["today_counts"].get(vertical, 0),
                weekly=report["weekly_counts"].get(vertical, 0),
            )
        )

    lines.extend(
        [
            f"Total Exported Jobs Today: {report['today_total']}",
            f"Total Jobs Exported Till Date: {report['weekly_total']}",
            "",
            "Failed Verticals",
            f"- {', '.join(report['failed_verticals']) or 'None'}",
            "",
            f"Attachment: {report['attachment_note']}",
        ]
    )

    return "\n".join(lines)


def build_html_body(report: dict) -> str:
    return f"""\
<html>
  <body style="font-family: Arial, sans-serif; color: #222;">
    <h2 style="margin-bottom: 8px;">Job Listings Summary - {escape(report['execution_date'].strftime('%d %b %Y'))}</h2>

    <h3 style="margin-top: 20px;">Export Summary</h3>
    {build_export_summary_table(report)}
    <p><strong>Total Exported Jobs Today:</strong> {report['today_total']}</p>
    <p><strong>Total Jobs Exported Till Date:</strong> {report['weekly_total']}</p>

    <h3 style="margin-top: 20px;">Failed Verticals</h3>
    {build_failed_verticals_html(report['failed_verticals'])}

    <h3 style="margin-top: 20px;">Attachment</h3>
    <p>{escape(report['attachment_note'])}</p>
  </body>
</html>
"""


def build_export_summary_table(report: dict) -> str:
    rows = []
    for vertical in report["vertical_order"]:
        rows.append(
            "<tr>"
            f"<td style=\"border: 1px solid #ccc; padding: 8px;\">{escape(vertical)}</td>"
            f"<td style=\"border: 1px solid #ccc; padding: 8px; text-align: right;\">{report['today_counts'].get(vertical, 0)}</td>"
            f"<td style=\"border: 1px solid #ccc; padding: 8px; text-align: right;\">{report['weekly_counts'].get(vertical, 0)}</td>"
            "</tr>"
        )

    return (
        "<table style=\"border-collapse: collapse; min-width: 420px;\">"
        "<tr>"
        "<th style=\"border: 1px solid #ccc; padding: 8px; text-align: left;\">Vertical</th>"
        "<th style=\"border: 1px solid #ccc; padding: 8px; text-align: right;\">Exported Jobs Today</th>"
        "<th style=\"border: 1px solid #ccc; padding: 8px; text-align: right;\">Total Jobs Exported Till Date</th>"
        "</tr>"
        + "".join(rows)
        + "</table>"
    )


def build_failed_verticals_html(failed_verticals: list[str]) -> str:
    if not failed_verticals:
        return "<p>None</p>"

    items = "".join(f"<li>{escape(vertical)}</li>" for vertical in failed_verticals)
    return f"<ul>{items}</ul>"


def attach_export_package(message: EmailMessage, summary: dict) -> str:
    export_files = [
        Path(file_path)
        for file_path in summary.get("export_files", [])
        if file_path
    ]
    export_files = [path for path in export_files if path.exists()]
    if not export_files:
        return "No export files were available to attach."

    zip_path = build_export_zip(export_files, summary)
    if zip_path is not None and zip_path.exists():
        with zip_path.open("rb") as file:
            message.add_attachment(
                file.read(),
                maintype="application",
                subtype="zip",
                filename=zip_path.name,
            )
        return f"Attached ZIP export package: {zip_path.name}"

    attached_files = []
    for path in export_files:
        with path.open("rb") as file:
            message.add_attachment(
                file.read(),
                maintype="text",
                subtype="csv",
                filename=path.name,
            )
        attached_files.append(path.name)

    return "Attached CSV exports: " + ", ".join(attached_files)


def describe_export_attachment(summary: dict) -> str:
    export_files = [
        Path(file_path)
        for file_path in summary.get("export_files", [])
        if file_path
    ]
    export_files = [path for path in export_files if path.exists()]
    if not export_files:
        return "No export files were available to attach."

    return "Current run export package is attached."


def build_export_zip(export_files: list[Path], summary: dict) -> Path | None:
    if not export_files:
        return None

    execution_dt_local = summary["started_at"].astimezone(LOCAL_TZ)
    zip_name = f"job_exports_{execution_dt_local.strftime('%Y%m%d')}.zip"
    zip_path = export_files[0].parent / zip_name

    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for export_file in export_files:
                archive.write(export_file, arcname=export_file.name)
    except OSError as error:
        logger.warning("Could not build export ZIP %s: %s", zip_path, error)
        return None

    return zip_path


def parse_history_date(value: object) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(str(value))
    except ValueError:
        parsed = parse_datetime(value)
        if parsed is None:
            return None
        return parsed.astimezone(LOCAL_TZ).date()
