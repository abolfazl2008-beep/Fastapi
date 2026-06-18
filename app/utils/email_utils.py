from typing import List


def parse_recipients(to_field: str) -> List[str]:
    return [e.strip().lower() for e in to_field.split(",") if e.strip()]


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"
