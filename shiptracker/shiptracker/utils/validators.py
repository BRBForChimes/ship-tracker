from typing import Optional, Union
from urllib.parse import urlparse
from shiptracker.utils.errors import InvalidInput

MAX_NAME = 64
MAX_TEXT = 1000


def clamp_text(s: Optional[str], *, max_len: int = MAX_TEXT) -> str:
    """
    Trim whitespace and enforce a max length.
    Returns an empty string for None/blank input (useful for 'clear' semantics).
    Raises InvalidInput if exceeding max_len.
    """
    s = (s or "").strip()
    if len(s) > max_len:
        raise InvalidInput(f"Text too long (>{max_len} chars).")
    return s


def validate_name(name: str) -> str:
    """
    1–64 chars after trimming. Raises InvalidInput otherwise.
    """
    name = (name or "").strip()
    if not (1 <= len(name) <= MAX_NAME):
        raise InvalidInput("Name must be 1–64 characters.")
    return name


def parse_bool_or_int(val: Union[str, bool, int]) -> int:
    """
    Accepts bool, int, or str forms of boolean (1/0, true/false, yes/no, on/off).
    Returns 1 or 0. Raises InvalidInput with the offending value on failure.
    """
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return 1 if val else 0

    v = (val or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return 1
    if v in {"0", "false", "no", "n", "off"}:
        return 0
    raise InvalidInput(f"Expected a boolean (true/false), got: {val!r}.")


def validate_url(u: Optional[str]) -> str:
    """
    Return a cleaned URL if valid (http/https), empty string if None/blank,
    otherwise raise InvalidInput with context.
    """
    if not u:
        return ""
    u = u.strip()
    parsed = urlparse(u)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return u
    raise InvalidInput(f"Invalid URL: {u!r}.")
