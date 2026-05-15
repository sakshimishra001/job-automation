# Job Curator

This project is a lightweight Python job curation pipeline for LMS job-listing feeds.

It fetches role-based jobs for configured verticals, keeps recent India-focused mid/senior roles, removes duplicates, and exports one CSV snapshot per vertical. It also keeps run state, a cross-run seen-jobs file, logs, and an optional email summary.

## Current Pipeline

1. Build role/location queries per vertical
2. Fetch jobs from enabled sources
3. Keep only recent jobs
4. Keep India-focused jobs from approved publishers
5. Classify seniority
6. Keep only `Mid` and `Senior`
7. Deduplicate within the run
8. Deduplicate against recent prior exports
9. Export per-vertical CSV snapshots
10. Save run state, seen jobs, logs, and optional email summary

## Project Structure

Core pipeline:

- `src/job_curator/main.py`
- `src/job_curator/fetch_jobs.py`
- `src/job_curator/filters.py`
- `src/job_curator/classify.py`
- `src/job_curator/dedupe.py`
- `src/job_curator/export_csv.py`
- `src/job_curator/operational_state.py`
- `src/job_curator/email_summary.py`

Source scrapers:

- `src/job_curator/sources/linkedin.py`
- `src/job_curator/sources/naukri.py`
- `src/job_curator/sources/indeed.py`
- `src/job_curator/sources/glassdoor.py`
- `src/job_curator/sources/common.py`

Configuration:

- `config/config.yaml`
- `.env`

Local scheduler helpers:

- `scripts/run_job_curator.ps1`
- `scripts/register_windows_task.ps1`

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## Environment Variables

Optional local `.env` values:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
EMAIL_FROM=...
EMAIL_TO=...
```

Runtime override variables:

```env
JOB_CURATOR_PROJECT_ROOT=...
JOB_CURATOR_CONFIG_FILE=...
JOB_CURATOR_ENV_FILE=...
JOB_CURATOR_OUTPUT_DIR=...
JOB_CURATOR_STATE_DIR=...
JOB_CURATOR_LOG_DIR=...
JOB_CURATOR_SEED_STATE_DIR=...
JOB_CURATOR_RECENT_JOB_WINDOW_DAYS=7
JOB_CURATOR_SEEN_RETENTION_DAYS=14
JOB_CURATOR_HEADLESS=true
JOB_CURATOR_EMAIL_ENABLED=false
```

These are mainly useful for Kaggle or server-side execution where the writable filesystem and secrets handling differ from local development.

## Run Locally

```powershell
python -m src.job_curator.main
```

Outputs:

- CSV snapshots: `data/raw/`
- state files: `data/state/`
- logs: `data/logs/job_curator.log`

## Kaggle Deployment

This project is compatible with Kaggle scheduled notebooks with a small amount of notebook setup.

### Recommended Kaggle Execution Model

1. Keep the code in GitHub
2. Copy or clone the repo into the Kaggle notebook working area
3. Install dependencies at notebook start
4. Install Playwright Chromium into a writable directory
5. Seed prior run state from a Kaggle input dataset if available
6. Run the pipeline
7. Keep CSVs, logs, and state files in `/kaggle/working`
8. Publish notebook outputs so the next scheduled run can reuse them

### Kaggle Notebook Setup

Example notebook cells:

```python
!pip install -r requirements.txt
```

```python
import os

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/kaggle/working/pw-browsers"
```

```python
!python -m playwright install chromium
```

```python
import os

os.environ["JOB_CURATOR_OUTPUT_DIR"] = "/kaggle/working/raw"
os.environ["JOB_CURATOR_STATE_DIR"] = "/kaggle/working/state"
os.environ["JOB_CURATOR_LOG_DIR"] = "/kaggle/working/logs"
os.environ["JOB_CURATOR_HEADLESS"] = "true"
```

If you attach the previous run's output dataset as an input, also set:

```python
os.environ["JOB_CURATOR_SEED_STATE_DIR"] = "/kaggle/input/<previous-output-dataset>/state"
```

Then run:

```python
!python -m src.job_curator.main
```

### Persistence on Kaggle

Kaggle notebook input datasets are read-only, while `/kaggle/working` is writable for the current run. Because of that:

- seed previous `run_state.json` and `seen_jobs.csv` from an attached input dataset
- write updated state to `/kaggle/working/state`
- publish notebook outputs at the end of the run
- attach the latest output dataset to the next scheduled run

This project now supports that flow with `JOB_CURATOR_SEED_STATE_DIR`.

### CSV Outputs on Kaggle

CSV exports remain useful as:

- backup output
- QA/debug artifact
- fallback handoff format

Even if the long-term LMS integration uses an API, CSV snapshots should still be retained for validation.

## GitHub Readiness

For GitHub:

- do not commit `.env`
- do not commit generated logs
- do not commit generated state unless you intentionally want seed examples
- keep `config/config.yaml` committed as the default business configuration

## Future LMS Integration

The clean production integration path is:

1. run the curation pipeline on scheduled infrastructure
2. produce curated structured job records
3. push final results into dashboard APIs
4. keep CSV exports as debug/backup artifacts

The current code is already structured so CSV export can remain as a backup while a future API upload step is added after curation.
