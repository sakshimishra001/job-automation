SENIOR_KEYWORDS = [
    "senior",
    "sr.",
    "sr",
    "lead",
    "principal",
    "director",
    "head",
    "vp",
    "chief",
]

MID_KEYWORDS = [
    "manager",
    "consultant",
    "strategist",
    "analyst",
]

VERTICAL_KEYWORDS = {
    "Product Management": [
        "product manager",
        "product management",
        "product owner",
        "product lead",
        "product strategy",
    ],
    "General Management": [
        "general manager",
        "chief of staff",
        "country manager",
        "business head",
        "operations head",
    ],
    "Project Management": [
        "project manager",
        "program manager",
        "pmo",
        "delivery manager",
        "scrum master",
    ],
    "Business Management": [
        "business manager",
        "business operations",
        "business strategy",
        "strategy manager",
        "operations manager",
    ],
    "Data Science": [
        "data scientist",
        "data science",
        "analytics",
        "data analyst",
        "decision science",
    ],
    "AI / Machine Learning": [
        "machine learning",
        "ml engineer",
        "artificial intelligence",
        "ai engineer",
        "genai",
        "deep learning",
    ],
    "Finance": [
        "finance",
        "financial",
        "fp&a",
        "investment",
        "treasury",
        "controller",
    ],
    "Digital Transformation": [
        "digital transformation",
        "transformation",
        "digital strategy",
        "process improvement",
        "automation",
        "erp",
    ],
}


def classify_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        title = clean_text(job.get("job_title", ""))
        description = clean_text(job.get("job_description", ""))
        searchable_text = f"{title} {description}"

        job["seniority_level"] = classify_seniority(title)
        job["vertical"] = classify_vertical(searchable_text)

    return jobs


def classify_seniority_for_jobs(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        title = clean_text(job.get("job_title", ""))
        job["seniority_level"] = classify_seniority(title)

    return jobs


def set_vertical_for_jobs(jobs: list[dict], vertical: str) -> list[dict]:
    for job in jobs:
        job["vertical"] = vertical

    return jobs


def classify_seniority(title: str) -> str:
    if contains_keyword(title, SENIOR_KEYWORDS):
        return "Senior"

    if contains_keyword(title, MID_KEYWORDS):
        return "Mid"

    return "unknown"


def classify_vertical(text: str) -> str:
    for vertical, keywords in VERTICAL_KEYWORDS.items():
        if contains_keyword(text, keywords):
            return vertical

    return "unknown"


def contains_keyword(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
