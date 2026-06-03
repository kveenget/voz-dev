import os


def enabled_categories() -> set[str]:
    raw = os.getenv("VOZ_TOOL_GROUPS", "coding,ide,git,mac,web,vision,notes")
    return {c.strip() for c in raw.split(",") if c.strip()}
