import re


SENIOR_KEYWORDS = [
    "senior",
    "lead",
    "principal",
    "director",
    "head",
]

MID_KEYWORDS = [
    "manager",
    "consultant",
    "strategist",
    "analyst",
]

EXECUTIVE_TITLE_KEYWORDS = [
    "chief",
    "cxo",
    "ceo",
    "coo",
    "cto",
    "cfo",
    "ciso",
    "chro",
    "vice president",
    "vp",
    "president",
    "executive director",
]

SENIOR_TITLE_KEYWORDS = [
    "senior",
    "lead",
    "principal",
    "director",
    "head",
    "staff",
]

MID_TITLE_KEYWORDS = [
    "manager",
    "consultant",
    "specialist",
    "analyst",
    "engineer",
    "scientist",
]

JUNIOR_TITLE_KEYWORDS = [
    "associate",
    "junior",
    "jr",
    "entry level",
    "trainee",
    "intern",
]

REMOTE_KEYWORDS = [
    "remote",
    "work from home",
    "wfh",
    "anywhere",
    "distributed",
]

HYBRID_KEYWORDS = [
    "hybrid",
]

ONSITE_KEYWORDS = [
    "onsite",
    "on site",
    "office based",
    "in office",
]

STRATEGY_TITLE_KEYWORDS = [
    "strategy",
    "strategic",
    "transformation",
    "planning",
    "growth",
    "corporate development",
    "chief of staff",
]

VERTICAL_KEYWORDS = {
    "Product Management": [
        "product manager",
        "product management",
        "product owner",
        "product lead",
        "product strategy",
        "product operations",
        "group product manager",
        "head of product",
        "vp product",
        "chief product officer",
    ],
    "Project Management": [
        "project manager",
        "program manager",
        "pmo",
        "delivery manager",
        "scrum master",
        "technical project manager",
        "project lead",
    ],
    "CXO / Executive Leadership": [
        "chief executive officer",
        "chief operating officer",
        "chief strategy officer",
        "chief technology officer",
        "chief ai officer",
        "chief information officer",
        "vice president",
        "vp ",
        "president",
        "executive leadership",
        "executive committee",
        "business unit head",
    ],
    "AI / ML": [
        "machine learning",
        "ml engineer",
        "artificial intelligence",
        "ai engineer",
        "ai product",
        "genai",
        "deep learning",
        "llm",
    ],
    "Data Science": [
        "data scientist",
        "data science",
        "analytics",
        "data analyst",
        "decision science",
        "business intelligence",
    ],
    "Finance": [
        "finance",
        "financial",
        "fp&a",
        "investment",
        "treasury",
        "controller",
        "fintech",
        "accounting",
    ],
    "HR": [
        "human resources",
        "talent acquisition",
        "hr manager",
        "people operations",
        "recruiter",
        "recruitment",
        "people partner",
    ],
    "Cybersecurity": [
        "cybersecurity",
        "information security",
        "security risk",
        "security engineer",
        "soc analyst",
        "threat",
        "application security",
        "cloud security",
    ],
    "Senior Management": [
        "senior manager",
        "lead manager",
        "general manager",
        "deputy general manager",
        "associate director",
        "director",
        "senior director",
        "avp",
        "vice president",
        "vp ",
        "functional head",
        "department head",
        "business unit head",
        "operations head",
        "program director",
        "delivery director",
        "regional manager",
        "country manager",
        "head of product",
        "head of engineering",
        "head of marketing",
        "head of finance",
        "head of hr",
        "head of operations",
    ],
    "Strategy Leadership": [
        "strategy manager",
        "senior strategy manager",
        "strategy lead",
        "business strategy manager",
        "corporate strategy manager",
        "corporate strategy lead",
        "strategic planning manager",
        "strategic initiatives lead",
        "transformation lead",
        "business transformation lead",
        "growth strategy manager",
        "chief of staff",
        "director strategy",
        "head of strategy",
        "vp strategy",
        "corporate development manager",
        "corporate development lead",
    ],
}


def classify_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        searchable_text = build_searchable_text(job)
        job["seniority_level"] = classify_seniority(job.get("job_title", ""))
        job["experience_bucket"] = classify_experience_bucket(job)
        job["vertical"] = classify_vertical(searchable_text)

    return jobs


def classify_seniority_for_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        job["seniority_level"] = classify_seniority(job.get("job_title", ""))
        job["experience_bucket"] = classify_experience_bucket(job)

    return jobs


def set_vertical_for_jobs(jobs: list[dict], vertical: str) -> list[dict]:
    for job in jobs:
        job["vertical"] = vertical

    return jobs


def validate_jobs_for_vertical(
    jobs: list[dict],
    vertical: str,
    min_score: int = 1,
) -> list[dict]:
    kept_jobs = []

    for job in jobs:
        title_text = clean_text(job.get("job_title", ""))
        searchable_text = build_searchable_text(job)

        if vertical == "Strategy Leadership" and not has_strategy_title_signal(title_text):
            continue

        if vertical == "Senior Management" and has_strategy_title_signal(title_text):
            continue

        best_vertical, best_score = classify_vertical_with_score(searchable_text)
        target_score = get_vertical_score(searchable_text, vertical)
        tie_verticals = [
            name for name, score in score_verticals(searchable_text).items()
            if score == best_score and score > 0
        ]

        if (
            target_score >= min_score
            and best_vertical == vertical
            and best_score > 0
            and len(tie_verticals) <= 2
        ):
            job["vertical_match_score"] = target_score
            kept_jobs.append(job)

    return kept_jobs


def classify_seniority(title: str) -> str:
    title_text = clean_text(title)

    if contains_keyword(title_text, EXECUTIVE_TITLE_KEYWORDS + SENIOR_KEYWORDS):
        return "Senior"

    if contains_keyword(title_text, MID_KEYWORDS):
        return "Mid"

    if contains_keyword(title_text, JUNIOR_TITLE_KEYWORDS):
        return "Junior"

    return "unknown"


def classify_experience_bucket(job: dict) -> str:
    text = build_searchable_text(job)
    title_text = clean_text(job.get("job_title", ""))
    years = extract_experience_years(text)

    if contains_keyword(title_text, EXECUTIVE_TITLE_KEYWORDS):
        return "Executive"

    if years is not None:
        if years <= 2:
            return "Junior"
        if years <= 10:
            return "Mid"
        if years <= 20:
            return "Senior"
        return "Executive"

    if contains_keyword(title_text, SENIOR_TITLE_KEYWORDS):
        return "Senior"
    if contains_keyword(title_text, MID_TITLE_KEYWORDS):
        return "Mid"
    if contains_keyword(title_text, JUNIOR_TITLE_KEYWORDS):
        return "Junior"

    return "Mid"


def classify_workplace_type(job: dict) -> str:
    raw_workplace_type = clean_text(job.get("job_workplace_type_raw", ""))
    if raw_workplace_type:
        if "remote" in raw_workplace_type:
            return "Remote"
        if "hybrid" in raw_workplace_type:
            return "Hybrid"
        if "on-site" in raw_workplace_type or "onsite" in raw_workplace_type or "on site" in raw_workplace_type:
            return "Onsite"

    employment_type = clean_text(job.get("job_employment_type", ""))
    searchable_text = build_searchable_text(job)
    combined_text = f"{employment_type} {searchable_text}".strip()

    if contains_keyword(combined_text, REMOTE_KEYWORDS):
        return "Remote"
    if contains_keyword(combined_text, HYBRID_KEYWORDS):
        return "Hybrid"
    if contains_keyword(combined_text, ONSITE_KEYWORDS):
        return "Onsite"

    return ""


def has_strategy_title_signal(title: str) -> bool:
    return contains_keyword(title, STRATEGY_TITLE_KEYWORDS)


def classify_vertical(text: str) -> str:
    vertical, score = classify_vertical_with_score(text)
    if score == 0:
        return "unknown"
    return vertical


def classify_vertical_with_score(text: str) -> tuple[str, int]:
    scores = score_verticals(text)
    if not scores:
        return "unknown", 0

    best_vertical = max(scores, key=scores.get)
    return best_vertical, scores[best_vertical]


def score_verticals(text: str) -> dict[str, int]:
    clean = clean_text(text)
    return {
        vertical: get_vertical_score(clean, vertical)
        for vertical in VERTICAL_KEYWORDS
    }


def get_vertical_score(text: str, vertical: str) -> int:
    clean = clean_text(text)
    keywords = VERTICAL_KEYWORDS.get(vertical, [])
    return sum(1 for keyword in keywords if keyword in clean)


def select_jobs_by_experience_bucket(
    jobs: list[dict],
    total_quota: int,
    bucket_quotas: dict[str, int],
) -> list[dict]:
    if total_quota <= 0 or not jobs:
        return []

    scaled_quotas = scale_bucket_quotas(bucket_quotas, total_quota)
    grouped_jobs = {bucket: [] for bucket in bucket_quotas}

    ordered_jobs = sort_jobs_for_selection(jobs)

    for job in ordered_jobs:
        bucket = job.get("experience_bucket", "Mid")
        grouped_jobs.setdefault(bucket, []).append(job)

    selected = []
    selected_ids = set()

    for bucket, limit in scaled_quotas.items():
        for job in grouped_jobs.get(bucket, [])[:limit]:
            job_id = id(job)
            if job_id not in selected_ids:
                selected.append(job)
                selected_ids.add(job_id)

    if len(selected) >= total_quota:
        return selected[:total_quota]

    remaining_jobs = []
    for bucket in ["Executive", "Senior", "Mid", "Junior"]:
        for job in grouped_jobs.get(bucket, []):
            if id(job) not in selected_ids:
                remaining_jobs.append(job)

    for job in remaining_jobs:
        if len(selected) >= total_quota:
            break
        selected.append(job)
        selected_ids.add(id(job))

    return selected


def scale_bucket_quotas(bucket_quotas: dict[str, int], target_total: int) -> dict[str, int]:
    configured_total = sum(bucket_quotas.values())
    if configured_total <= 0:
        return {bucket: 0 for bucket in bucket_quotas}

    scaled = {}
    remainders = []
    assigned_total = 0

    for bucket, count in bucket_quotas.items():
        raw_value = (count / configured_total) * target_total
        base_value = int(raw_value)
        scaled[bucket] = base_value
        assigned_total += base_value
        remainders.append((raw_value - base_value, bucket))

    for _, bucket in sorted(remainders, reverse=True):
        if assigned_total >= target_total:
            break
        scaled[bucket] += 1
        assigned_total += 1

    return scaled


def sort_jobs_for_selection(jobs: list[dict]) -> list[dict]:
    return sorted(
        jobs,
        key=lambda job: (
            -int(job.get("vertical_match_score", 0) or 0),
            experience_priority(job),
            title_seniority_priority(job),
        ),
    )


def experience_priority(job: dict) -> int:
    bucket = clean_text(job.get("experience_bucket", ""))
    order = {
        "executive": 0,
        "senior": 1,
        "mid": 2,
        "junior": 3,
    }
    return order.get(bucket, 4)


def title_seniority_priority(job: dict) -> int:
    title = clean_text(job.get("job_title", ""))
    if contains_keyword(title, EXECUTIVE_TITLE_KEYWORDS):
        return 0
    if contains_keyword(title, SENIOR_TITLE_KEYWORDS):
        return 1
    if contains_keyword(title, MID_TITLE_KEYWORDS):
        return 2
    if contains_keyword(title, JUNIOR_TITLE_KEYWORDS):
        return 3
    return 4


def extract_experience_years(text: str) -> int | None:
    clean = clean_text(text)
    patterns = [
        r"(\d+)\s*\+?\s*(?:years|yrs)",
        r"(\d+)\s*-\s*(\d+)\s*(?:years|yrs)",
        r"(\d+)\s*to\s*(\d+)\s*(?:years|yrs)",
    ]

    for pattern in patterns:
        match = re.search(pattern, clean)
        if not match:
            continue

        numbers = [int(value) for value in match.groups() if value is not None]
        if numbers:
            return max(numbers)

    return None


def build_searchable_text(job: dict) -> str:
    parts = [
        clean_text(job.get("job_title", "")),
        clean_text(job.get("job_description", "")),
        clean_text(job.get("job_search_text", "")),
        clean_text(job.get("job_employment_type", "")),
        clean_text(job.get("job_location", "")),
        clean_text(job.get("job_city", "")),
    ]
    return " ".join(part for part in parts if part)


def contains_keyword(text: str, keywords: list[str]) -> bool:
    clean = clean_text(text)
    return any(keyword in clean for keyword in keywords)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
