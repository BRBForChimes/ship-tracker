from urllib.parse import urlparse
from shiptracker.utils.errors import InvalidInput

MAX_NAME = 64
MAX_TEXT = 1000

def clamp_text(s: str, *, max_len: int = MAX_TEXT) -> str:
    s = s.strip()
    if len(s) > max_len:
        raise InvalidInput(f"Text too long (>{max_len} chars).")
    return s

def validate_name(name: str) -> str:
    name = name.strip()
    if not (1 <= len(name) <= MAX_NAME):
        raise InvalidInput("Name must be 1–64 characters.")
    return name

def parse_bool_or_int(val: str | bool | int) -> int:
    if isinstance(val, bool): return int(val)
    if isinstance(val, int): return 1 if val else 0
    v = val.lower()
    if v in {"1","true","yes","y","on"}: return 1
    if v in {"0","false","no","n","off"}: return 0
    raise InvalidInput("Expected a boolean (true/false).")

def validate_url(u: str) -> str:
    if not u: return u
    parsed = urlparse(u)
    if parsed.scheme in {"http","https"} and parsed.netloc:
        return u
    raise InvalidInput("Invalid URL.")
