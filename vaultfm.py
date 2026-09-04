"""Shared YAML-frontmatter handling for the vault tooling.

Extracted because three tools carried their own copy of the same set-scalar function
and two carried their own parser. The edge cases these hit — folded scalars, quoted
colons, multi-line values, unfilled template placeholders — are identical in all of
them, so a fix in one copy silently left the others broken.

Deliberately NOT a YAML library: these files are hand-edited markdown where a strict
parser would reject documents the vault considers fine, and the write path must
preserve byte-for-byte everything it does not explicitly change.
"""
import re

FM_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.S)

MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
_DATE_ISO = re.compile(r'^(\d{4})-(\d{2})-(\d{2})')
_DATE_DMY = re.compile(r'^(\d{2})/(\d{2})/(\d{4})')
_DATE_MDY = re.compile(r'^([A-Z][a-z]{2})\w*\s+(\d{1,2}),?\s+(\d{4})')


def split(text):
    """(frontmatter_text, body, lines_consumed). No frontmatter -> ('', text, 0)."""
    m = FM_RE.match(text)
    return (m.group(1), text[m.end():], text[:m.end()].count("\n")) if m else ("", text, 0)


def scalar(fm, key):
    m = re.search(rf'^{re.escape(key)}:[ \t]*(.*)$', fm, re.M)
    return m.group(1).strip().strip('"\'') if m else ""


def yaml_list(fm, key):
    """Inline [a, b] or a following block of '- ' items."""
    m = re.search(rf'^{re.escape(key)}:[ \t]*(.*)$', fm, re.M)
    if not m: return []
    inline = m.group(1).strip()
    if inline.startswith("["):
        return [x.strip().strip('"\'') for x in inline.strip("[]").split(",") if x.strip()]
    out = []
    for line in fm[m.end():].splitlines():
        if re.match(r'^\s*-\s+', line):
            out.append(re.sub(r'^\s*-\s+', '', line).strip().strip('"\''))
        elif line.strip() and not line[:1].isspace():
            break
    return out


def folded(fm, key):
    """Value of a folded/literal scalar (`key: >`), joined. Falls back to the inline
    value. Four skills used `description: >` and a naive parser returned a bare '>'."""
    m = re.search(rf'^{re.escape(key)}:[ \t]*(.*)$', fm, re.M)
    if not m: return ""
    v = m.group(1).strip().strip('"\'')
    if v and not re.fullmatch(r'[>|][-+]?\d*', v):
        return v
    parts = []
    for line in fm[m.end():].splitlines():
        if line.strip() and not line[:1].isspace():
            break
        if line.strip():
            parts.append(line.strip())
    return " ".join(parts)


def set_scalar(fm, key, value):
    """Replace or append ONE key. Never reserialises — every other line is preserved
    byte-for-byte, which is what lets these tools write to a live vault safely.
    Single-line scalars only; use the block helpers for list values."""
    if re.search(rf'^{re.escape(key)}:', fm, re.M):
        return re.sub(rf'^{re.escape(key)}:.*$', f'{key}: {value}', fm, count=1, flags=re.M)
    return fm.rstrip("\n") + f"\n{key}: {value}"


def norm_date(v):
    """Normalise to ISO. Raw string comparison silently excluded 'Sep 3, 2026',
    '03/09/2026' and journal-style '2026_09_04' from any --since cutoff."""
    v = str(v or "").strip().strip('"\'')
    if not v or v.lower() in ("null", "none", "~") or v.startswith("{{"):
        return ""
    v = v.replace("_", "-")
    m = _DATE_ISO.match(v)
    if m: return f"{m[1]}-{m[2]}-{m[3]}"
    m = _DATE_DMY.match(v)
    if m: return f"{m[3]}-{m[2]}-{m[1]}"
    m = _DATE_MDY.match(v)
    if m:
        mon = MONTHS.get(m[1][:3])
        if mon: return f"{m[3]}-{mon}-{int(m[2]):02d}"
    return v[:10]
