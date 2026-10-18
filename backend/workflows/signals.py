"""Rule-based signals shared by screening and moderation (English + Bangla)."""
from __future__ import annotations

import re

from agent.guardrails import EMAIL_RE, PHONE_RE, BN_PHONE_RE, looks_like_injection

SCAM_PATTERNS = {
    "advance before visit": r"(advance|deposit|payment|টাকা|অগ্রিম).{0,40}(before|without|আগে).{0,20}(visit|viewing|seeing|দেখা)",
    "mobile-money advance": r"(send|pay|transfer|পাঠান|পাঠাও).{0,30}(bkash|b-kash|nagad|rocket|বিকাশ|নগদ)|"
                            r"(bkash|nagad|rocket|বিকাশ|নগদ).{0,30}(advance|first|to book|অগ্রিম|আগে)",
    "owner unavailable / no visit": r"owner (is )?(abroad|outside|overseas)|no visit|visit (is )?not possible|"
                                    r"keys? (will be )?(couriered|sent)|দেখা যাবে না|বিদেশে থাকেন",
    "pressure tactics": r"first come,? first served|very urgent|urgent!+|today only|শুধু আজ",
    "off-platform contact": r"whats ?app only|contact (me )?on whats ?app|telegram only|t\.me/",
}
_SCAM = {k: re.compile(v, re.IGNORECASE) for k, v in SCAM_PATTERNS.items()}

SPAM_PATTERNS = [r"https?://", r"\bbit\.ly\b", r"\bt\.me/", r"earn (money|\$|taka)", r"\bdiscount\b",
                 r"\bcall now\b", r"\bvisit my (page|profile|channel)\b", r"\bfollow me\b", r"\bpromo(tion)? code\b"]
_SPAM = re.compile("|".join(SPAM_PATTERNS), re.IGNORECASE)

# A deliberately small list of unambiguous slurs/abuse. The LLM reviewer covers subtler cases.
ABUSE_WORDS = ["idiot", "stupid", "bastard", "slut", "whore", "fuck", "f\\*ck", "bitch", "i will kill",
               "হারামি", "কুত্তা", "শালা", "মাগি", "বেশ্যা", "খানকি"]
_ABUSE = re.compile("|".join(ABUSE_WORDS), re.IGNORECASE)


def scam_signals(text: str) -> list[str]:
    return [name for name, rx in _SCAM.items() if rx.search(text or "")]


def content_signals(text: str) -> dict[str, str]:
    """label -> human-readable reason"""
    text = text or ""
    found: dict[str, str] = {}
    if EMAIL_RE.search(text) or PHONE_RE.search(text) or BN_PHONE_RE.search(text):
        found["personal_info"] = "contains a phone number or email address"
    if looks_like_injection(text):
        found["prompt_injection"] = "contains instructions aimed at AI assistants"
    spam_hits = len(_SPAM.findall(text))
    letters = [c for c in text if c.isalpha() and c.isascii()]
    if spam_hits >= 2 or (len(letters) > 40 and sum(c.isupper() for c in letters) / len(letters) > 0.7) \
            or re.search(r"(.)\1{9,}", text):
        found["spam"] = "looks like spam (links, promotions or shouting)"
    if m := _ABUSE.search(text):
        found["abuse"] = f"abusive language (“{m.group(0)}”)"
    return found
