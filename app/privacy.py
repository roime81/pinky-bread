import re
from dataclasses import dataclass, field


@dataclass
class ScrubResult:
    text: str
    token_map: dict[str, str] = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)


PATTERNS = [
    ("NRIC", re.compile(r"(?<!\d)\d{6}-?\d{2}-?\d{4}(?!\d)")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
]


def scrub_text(text: str) -> ScrubResult:
    token_map: dict[str, str] = {}
    findings: list[str] = []
    output = text
    for label, pattern in PATTERNS:
        matches = list(dict.fromkeys(m.group(0) for m in pattern.finditer(output)))
        for value in matches:
            token = f"<{label}_{len(token_map) + 1}>"
            token_map[token] = value
            output = output.replace(value, token)
            findings.append(label)
    return ScrubResult(text=output, token_map=token_map, findings=sorted(set(findings)))
