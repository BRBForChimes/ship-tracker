import discord
from typing import Dict, Any, Optional


# ---- tiny helpers -----------------------------------------------------------

def _clean(v: Optional[Any]) -> str:
    """Trim to a string; return '' if None/blank."""
    return str(v).strip() if v is not None else ""

def _damage_str(v: Any) -> Optional[str]:
    """Clamp to 0–5, return as string, or None if invalid."""
    try:
        n = max(0, min(5, int(v)))
        return str(n)
    except (TypeError, ValueError):
        return None

def _add_inline_triplet(embed: discord.Embed, *pairs: str):
    """
    Add up to three inline fields given as (name, value) pairs.
    Skips any pair whose value is blank after cleaning.
    """
    for name, value in zip(pairs[::2], pairs[1::2]):
        val = _clean(value)
        if val:
            embed.add_field(name=name, value=val, inline=True)

def _squad_lock_text(epoch: Any) -> Optional[str]:
    """Return a Discord timestamp '<t:...:f>' or None if invalid/unset."""
    try:
        ts = int(epoch)
        return f"<t:{ts}:f>" if ts > 0 else None
    except (TypeError, ValueError):
        return None

def _color_for_status(status: str) -> discord.Colour:
    s = (status or "").strip().lower()
    if s == "deployed":
        return discord.Colour.blue()
    if s == "repairing":
        return discord.Colour.orange()
    if s == "dead":
        return discord.Colour.dark_grey()
    # default for "Parked" and anything else
    return discord.Colour.green()


# ---- public API -------------------------------------------------------------

def ship_main_embed(ship: Dict[str, Any]) -> discord.Embed:
    """
    Card layout:
      Title: Ship Name
      Row 1 (inline): Type · Status · Damage
      Row 2 (inline): Location · Home Port · Regiment
      Block: Keys
      Block: Squad Lock  (rendered as <t:timestamp:f>)
      Block: Notes
      Image: if image_url present
    (Skip any empty field without showing placeholder characters.)
    """
    title = _clean(ship.get("name")) or "Unnamed Ship"
    status = _clean(ship.get("status")) or "Parked"

    embed = discord.Embed(title=title, colour=_color_for_status(status))

    # Row 1
    _add_inline_triplet(
        embed,
        "Type",    ship.get("type"),
        "Status",  status,
        "Damage",  _damage_str(ship.get("damage")),
    )

    # Row 2
    _add_inline_triplet(
        embed,
        "Location",  ship.get("location"),
        "Home Port", ship.get("home_port"),
        "Regiment",  ship.get("regiment"),
    )

    # Keys
    keys = _clean(ship.get("keys"))
    if keys:
        embed.add_field(name="Keys", value=keys, inline=False)

    # Squad Lock
    lock_text = _squad_lock_text(ship.get("squad_lock_until"))
    if lock_text:
        embed.add_field(name="Squad Lock", value=lock_text, inline=False)

    # Notes
    notes = _clean(ship.get("notes"))
    if notes:
        # Clamp to 1024 chars (Discord field value limit)
        val = notes if len(notes) <= 1024 else (notes[:1024 - 1] + "…")
        embed.add_field(name="Notes", value=val, inline=False)

    img_url = _clean(ship.get("image_url") or ship.get("image"))
    
    if img_url:
        embed.set_image(url=img_url)
    return embed


