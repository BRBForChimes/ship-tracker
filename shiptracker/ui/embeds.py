import time
import discord
from typing import Dict, Any

def _val(v: Any) -> str:
    """Render empty-ish values as an em dash for cleaner embeds."""
    if v is None: return "—"
    s = str(v).strip()
    return s if s else "—"

def _damage_int(v: Any) -> int:
    """Clamp to 0–5 and default to 0 if not an int."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, n))

def _squad_lock_text(epoch: Any) -> str:
    """Return <t:timestamp> or '—' if not set."""
    try:
        e = int(epoch)
        if e > 0:
            return f"<t:{e}:f>"
    except (TypeError, ValueError):
        pass
    return "—"

def ship_main_embed(ship: Dict[str, Any]) -> discord.Embed:
    """
    Main ship embed (no buttons here—just the card).
    Layout:
      # Ship Name (title)
      Type - Status - Damage
      Location - Home Port - Regiment
      Keys
      Squad Lock: <t:timestamp>
      Notes (if any)
      Image (if set)
    """
    name = ship.get("name", "Unnamed Ship")
    e = discord.Embed(title=f"🚢 {name}")

    # Row 1: Type - Status - Damage(0–5)
    type_ = _val(ship.get("type"))
    status = _val(ship.get("status"))
    damage = _damage_int(ship.get("damage"))
    row1 = f"{type_} — {status} — Damage {damage}"
    e.add_field(name="\u200b", value=row1, inline=False)

    # Row 2: Location - Home Port - Regiment
    location = _val(ship.get("location"))
    home_port = _val(ship.get("home_port"))
    regiment = _val(ship.get("regiment"))
    row2 = f"{location} — {home_port} — {regiment}"
    e.add_field(name="\u200b", value=row2, inline=False)

    # Keys
    keys = _val(ship.get("keys"))
    e.add_field(name="Keys", value=keys, inline=False)

    # Squad Lock (info-only timer)
    lock_txt = _squad_lock_text(ship.get("squad_lock_until"))
    e.add_field(name="Squad Lock", value=lock_txt, inline=False)

    # Notes (only add if present)
    notes = str(ship.get("notes") or "").strip()
    if notes:
        # Discord limits field values to 1024 chars; trim just in case
        e.add_field(name="Notes", value=(notes[:1024] + ("…" if len(notes) > 1024 else "")), inline=False)

    # Image (if set)
    img = str(ship.get("image_url") or "").strip()
    if img:
        e.set_image(url=img)

    return e
