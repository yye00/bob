"""Unicode sanitizer for auto-generated CLAUDE.md content.

Defends against the "Rules File Backdoor" attack (Pillar Security, 2025)
where adversarial Unicode in CLAUDE.md/.cursorrules can manipulate AI behavior.
"""
import unicodedata


# Unicode categories to strip — characters that can hide or distort content
_BLOCKED_CATEGORIES = frozenset({"Cf", "Cc", "Co", "Cs"})

# Cc codepoints that are safe and must be preserved
_ALLOWED_CC = frozenset({"\n", "\t"})


def sanitize_for_claude_md(text: str) -> str:
    """Return a sanitized copy of text safe for inclusion in CLAUDE.md.

    Applies NFKC normalization, then strips Unicode codepoints in categories
    Cf (format), Cc (control), Co (private use), and Cs (surrogate), keeping
    only \\n and \\t from the Cc category.
    """
    normalized = unicodedata.normalize("NFKC", text)
    chars = []
    for ch in normalized:
        cat = unicodedata.category(ch)
        if cat in _BLOCKED_CATEGORIES and ch not in _ALLOWED_CC:
            continue
        chars.append(ch)
    return "".join(chars)
