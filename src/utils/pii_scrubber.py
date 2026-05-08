import re
from typing import NamedTuple

class ScrubResult(NamedTuple):
    text: str
    hits: int

# Rules: (Regex, Replacement)
_RULES = [
    (re.compile(r"(?:\+84|0)(?:3|5|7|8|9)\d{8}\b"), "[SĐT]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[Email]"),
    (re.compile(r"\b\d{9,12}\b"), "[ID]"),
]

def scrub(text: str) -> ScrubResult:
    total_hits = 0
    scrubbed_text = text
    
    for pattern, replacement in _RULES:
        scrubbed_text, count = pattern.subn(replacement, scrubbed_text)
        total_hits += count
        
    return ScrubResult(text=scrubbed_text, hits=total_hits)
