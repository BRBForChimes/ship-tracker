# shiptracker/ui/views.py
import time
import asyncio
import discord
from typing import Optional, Iterable

from shiptracker.ui.embeds import ship_main_embed
from shiptracker.ui.modals import (
    ReturnModal, StartRepairsModal, FinishRepairsModal, NotesModal,
    EditModal, LogModal, AddUserModal, CreateShipModal
)
from shiptracker.utils.locks import with_lock
from shiptracker.utils.updater import update_all_instances

# -----------------------------------------------------------------------------
# Custom ID helpers
# -----------------------------------------------------------------------------
# Format: st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}
def make_cid(ship_id: int, war_id: int, mode: str, action: str) -> str:
    return f"st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}"

def parse_cid(custom_id: str) -> dict:
    parts = custom_id.split(":")
    try:
        return {"ship_id": int(parts[2]), "war_id": int(parts[4]), "mode": parts[6], "action": parts[8]}
    except Exception:
        return {"action": "invalid"}


# -----------------------------------------------------------------------------
# Small utils
# -----------------------------------------------------------------------------
def _status(ship: dict) -> str:
    return (ship.get("status") or "").strip()

def safe_join_lines(lines: Iterable[str], max_chars: int = 1900) -> str:
    """Join bullet lines without exceeding Discord's 2000 char limit."""
    out, total = [], 0
    for line in lines:
        need = len(line) + 1  # newline
        if total + need > max_chars:
            break
        out.append(line)
        total += need
    return "\n".join(out)

async def require_ship_auth(i: discord.Interaction, ship_guild_id: int, ship_name: str) -> bool:
    """Cross-guild ship authorization: authorized in any related guild or per-ship."""
    ok = await i.client.service_auth.user_is_authorized_for_ship_any_guild(
        ship_guild_id, ship_name, i.user.id
    )
    if not ok:
        if not i.response.is_done():
            await i.response.send_message("You’re not authorized for this ship.", ephemeral=True)
        else:
            await i.followup.send("You’re not authorized for this ship.", ephemeral=True)
    return ok


# -----------------------------------------------------------------------------
# Persistent View for ship cards
# -----------------------------------------------------------------------------
class ShipView(discord.ui.View):
    def __init__(self, ship: dict, mode: str = "main"):
        super().__init__(timeout=None)
        self.ship_id = int(ship["id"])
        self.war_id = int(ship["war_id"])
        self.mode = mode
        self._build(ship)

    def _build(self, ship: dict):
        self.clear_items()
        status = (ship.get("status") or "").strip().lower()

        if self.mode == "main":
            # Row 0: core actions
            if status in {"repairing", "deployed"}:
                self.add_item(discord.ui.Button(
                    label="Return",
                    style=discord.ButtonStyle.primary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "return_modal"),
                    row=0,
                ))
            else:
                self.add_item(discord.ui.Button(
                    label="Depart",
                    style=discord.ButtonStyle.primary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "depart"),
                    row=0,
                ))

            if status == "repairing":
                self.add_item(discord.ui.Button(
                    label="Finish Repairs",
                    style=discord.ButtonStyle.success,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "finish_repairs_modal"),
                    row=0,
                ))
            else:
                self.add_item(discord.ui.Button(
                    label="Repair",
                    style=discord.ButtonStyle.secondary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "start_repairs_modal"),
                    row=0,
                ))

            self.add_item(discord.ui.Button(
                emoji="⏰",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "refresh_lock"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="📝",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "notes_modal"),
                row=0,
            ))

            # Row 1: mode switches
            self.add_item(discord.ui.Button(
                label="Manage",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_manage"),
                row=1,
            ))
            self.add_item(discord.ui.Button(
                label="Info",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_info"),
                row=1,
            ))

        elif self.mode == "manage":
            # Row 0: manage actions
            self.add_item(discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "edit_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "log_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="🔗", label="Share",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "share_code"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="➕", label="Add User",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "add_user_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="💀", label="Kill",
                style=discord.ButtonStyle.danger,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "kill_confirm"),
                row=0,
            ))

            # Row 1: back only
            self.add_item(discord.ui.Button(
                label="◀ Back",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "switch_main"),
                row=1,
            ))

        elif self.mode == "info":
            # Row 0: info actions
            self.add_item(discord.ui.Button(
                label="Actions",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_actions"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Kill Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_kills"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Op Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_ops"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Info Dump",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "info_dump"),
                row=0,
            ))

            # Row 1: back only
            self.add_item(discord.ui.Button(
                label="◀ Back",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "switch_main"),
                row=1,
            ))


# -----------------------------------------------------------------------------
# Helpers to refresh all posted instances of a ship
# -----------------------------------------------------------------------------
async def _refresh_everywhere(client: discord.Client, ship_id: int):
    fresh = await client.db.get_ship_by_id(ship_id)
    instances = await client.db.get_instances(ship_id)
    if not instances:
        return

    async def build_embed():
        return ship_main_embed(fresh)

    def build_view():
        return ShipView(fresh, mode="main")

    await update_all_instances(client, instances, build_embed, build_view)
    
# -----------------------------------------------------------------------------
# Component Router
# -----------------------------------------------------------------------------
async def handle_component(interaction: discord.Interaction):
    if interaction.type is not discord.InteractionType.component:
        return
    data = interaction.data or {}
    cid = data.get("custom_id")
    if not cid or not cid.startswith("st:ship:"):
        return

    bits = parse_cid(cid)
    action = bits.get("action", "invalid")

    ship = await interaction.client.db.get_ship_by_id(bits["ship_id"])
    if not ship:
        await interaction.response.send_message("Ship not found.", ephemeral=True)
        return

    # Top-level auth guard for all component interactions
    if not await require_ship_auth(interaction, ship["guild_id"], ship["name"]):
        return

    service = interaction.client.service

    # ---------- MAIN actions ----------
    if action == "depart":
        # (Re-check optional; already gated above)
        async def do():
            await service.depart(ship["id"], interaction.user.id)
        await with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message("Status set to **Deployed**.", ephemeral=True)
        return

    if action == "return_modal":
        modal = ReturnModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.return_to_port(
                    ship["id"], i.user.id,
                    modal.where.value, modal.smokes.value, modal.notes.value
                )
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Returned and updated.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "start_repairs_modal":
        modal = StartRepairsModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.start_repairs(ship["id"], i.user.id, modal.where.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs started.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "finish_repairs_modal":
        modal = FinishRepairsModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.finish_repairs(ship["id"], i.user.id, modal.where.value, modal.notes.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs finished: set to **Parked**.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "refresh_lock":
        # Guard (already checked above)
        async def do():
            return await service.refresh_squad_lock(ship["id"], interaction.user.id, days=2)
        ts = await with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message(f"Squad lock recorded until <t:{ts}:f>.", ephemeral=True)
        return

    if action == "notes_modal":
        modal = NotesModal(existing=ship.get("notes"))

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.set_notes(ship["id"], i.user.id, modal.notes.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Notes updated.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "switch_manage":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="manage"))
        return

    if action == "switch_info":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="info"))
        return

    if action == "switch_main":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="main"))
        return

    # ---------- MANAGE actions ----------
    if action == "edit_modal":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        modal = EditModal(fresh)

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            dmg_txt = modal.damage.value.strip()
            dmg = max(0, min(5, int(dmg_txt))) if dmg_txt.isdigit() else 0
            fields = {
                "name": modal.name.value.strip(),
                "status": modal.status.value.strip(),
                "damage": dmg,
                "location": (modal.location.value or "").strip() or None,
                "keys": (modal.keys.value or "").strip() or None,
            }
            async def do():
                await i.client.service.edit_fields_bulk(ship["id"], i.user.id, fields)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Edited ship.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "log_modal":
        modal = LogModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.log_kill_and_op(ship["id"], i.user.id, modal.kills.value, modal.debrief.value)
            await with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("Logged.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "share_code":
        # Guard (already checked above)
        async def do():
            return await service.gen_one_time_share_code(ship["id"], interaction.user.id)
        code = await with_lock(f"ship:{ship['id']}", do)
        await interaction.response.send_message(
            f"One-time share code: **{code}** (consumed on first use).",
            ephemeral=True
        )
        return

    if action == "add_user_modal":
        modal = AddUserModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.add_ship_auth_user_text(ship["id"], modal.user.value, i.user.id)
            await with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("User authorized on this ship.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

# shiptracker/ui/views.py
import time
import asyncio
import discord
from typing import Optional, Iterable

from shiptracker.ui.embeds import ship_main_embed
from shiptracker.ui.modals import (
    ReturnModal, StartRepairsModal, FinishRepairsModal, NotesModal,
    EditModal, LogModal, AddUserModal, CreateShipModal
)
from shiptracker.utils.locks import with_lock


# -----------------------------------------------------------------------------
# Custom ID helpers
# -----------------------------------------------------------------------------
# Format: st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}
def make_cid(ship_id: int, war_id: int, mode: str, action: str) -> str:
    return f"st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}"

def parse_cid(custom_id: str) -> dict:
    parts = custom_id.split(":")
    try:
        return {"ship_id": int(parts[2]), "war_id": int(parts[4]), "mode": parts[6], "action": parts[8]}
    except Exception:
        return {"action": "invalid"}


# -----------------------------------------------------------------------------
# Small utils
# -----------------------------------------------------------------------------
def _status(ship: dict) -> str:
    return (ship.get("status") or "").strip()

def safe_join_lines(lines: Iterable[str], max_chars: int = 1900) -> str:
    """Join bullet lines without exceeding Discord's 2000 char limit."""
    out, total = [], 0
    for line in lines:
        need = len(line) + 1  # newline
        if total + need > max_chars:
            break
        out.append(line)
        total += need
    return "\n".join(out)

async def require_ship_auth(i: discord.Interaction, ship_guild_id: int, ship_name: str) -> bool:
    """Cross-guild ship authorization: authorized in any related guild or per-ship."""
    ok = await i.client.service_auth.user_is_authorized_for_ship_any_guild(
        ship_guild_id, ship_name, i.user.id
    )
    if not ok:
        if not i.response.is_done():
            await i.response.send_message("You’re not authorized for this ship.", ephemeral=True)
        else:
            await i.followup.send("You’re not authorized for this ship.", ephemeral=True)
    return ok


# -----------------------------------------------------------------------------
# Persistent View for ship cards
# -----------------------------------------------------------------------------
class ShipView(discord.ui.View):
    def __init__(self, ship: dict, mode: str = "main"):
        super().__init__(timeout=None)
        self.ship_id = int(ship["id"])
        self.war_id = int(ship["war_id"])
        self.mode = mode
        self._build(ship)

    def _build(self, ship: dict):
        self.clear_items()
        status = (ship.get("status") or "").strip().lower()

        if self.mode == "main":
            # Row 0: core actions
            if status in {"repairing", "deployed"}:
                self.add_item(discord.ui.Button(
                    label="Return",
                    style=discord.ButtonStyle.primary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "return_modal"),
                    row=0,
                ))
            else:
                self.add_item(discord.ui.Button(
                    label="Depart",
                    style=discord.ButtonStyle.primary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "depart"),
                    row=0,
                ))

            if status == "repairing":
                self.add_item(discord.ui.Button(
                    label="Finish Repairs",
                    style=discord.ButtonStyle.success,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "finish_repairs_modal"),
                    row=0,
                ))
            else:
                self.add_item(discord.ui.Button(
                    label="Repair",
                    style=discord.ButtonStyle.secondary,
                    custom_id=make_cid(self.ship_id, self.war_id, "main", "start_repairs_modal"),
                    row=0,
                ))

            self.add_item(discord.ui.Button(
                emoji="⏰",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "refresh_lock"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="📝",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "notes_modal"),
                row=0,
            ))

            # Row 1: mode switches
            self.add_item(discord.ui.Button(
                label="Manage",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_manage"),
                row=1,
            ))
            self.add_item(discord.ui.Button(
                label="Info",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_info"),
                row=1,
            ))

        elif self.mode == "manage":
            # Row 0: manage actions
            self.add_item(discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "edit_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "log_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="🔗", label="Share",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "share_code"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="➕", label="Add User",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "add_user_modal"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                emoji="💀", label="Kill",
                style=discord.ButtonStyle.danger,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "kill_confirm"),
                row=0,
            ))

            # Row 1: back only
            self.add_item(discord.ui.Button(
                label="◀ Back",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "manage", "switch_main"),
                row=1,
            ))

        elif self.mode == "info":
            # Row 0: info actions
            self.add_item(discord.ui.Button(
                label="Actions",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_actions"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Kill Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_kills"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Op Log",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "show_ops"),
                row=0,
            ))
            self.add_item(discord.ui.Button(
                label="Info Dump",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "info_dump"),
                row=0,
            ))

            # Row 1: back only
            self.add_item(discord.ui.Button(
                label="◀ Back",
                style=discord.ButtonStyle.secondary,
                custom_id=make_cid(self.ship_id, self.war_id, "info", "switch_main"),
                row=1,
            ))


# -----------------------------------------------------------------------------
# Helpers to refresh all posted instances of a ship
# -----------------------------------------------------------------------------

async def _refresh_everywhere(client: discord.Client, ship_id: int):
    fresh = await client.db.get_ship_by_id(ship_id)
    instances = await client.db.get_instances(ship_id)
    if not instances:
        return

    async def build_embed():
        return ship_main_embed(fresh)

    def build_view():
        return ShipView(fresh, mode="main")

    await update_all_instances(client, instances, build_embed, build_view)
# -----------------------------------------------------------------------------
# Component Router
# -----------------------------------------------------------------------------
async def handle_component(interaction: discord.Interaction):
    if interaction.type is not discord.InteractionType.component:
        return
    data = interaction.data or {}
    cid = data.get("custom_id")
    if not cid or not cid.startswith("st:ship:"):
        return

    bits = parse_cid(cid)
    action = bits.get("action", "invalid")

    ship = await interaction.client.db.get_ship_by_id(bits["ship_id"])
    if not ship:
        await interaction.response.send_message("Ship not found.", ephemeral=True)
        return

    # Top-level auth guard for all component interactions
    if not await require_ship_auth(interaction, ship["guild_id"], ship["name"]):
        return

    service = interaction.client.service

    # ---------- MAIN actions ----------
    if action == "depart":
        # (Re-check optional; already gated above)
        async def do():
            await service.depart(ship["id"], interaction.user.id)
        await with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message("Status set to **Deployed**.", ephemeral=True)
        return

    if action == "return_modal":
        modal = ReturnModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.return_to_port(
                    ship["id"], i.user.id,
                    modal.where.value, modal.smokes.value, modal.notes.value
                )
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Returned and updated.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "start_repairs_modal":
        modal = StartRepairsModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.start_repairs(ship["id"], i.user.id, modal.where.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs started.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "finish_repairs_modal":
        modal = FinishRepairsModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.finish_repairs(ship["id"], i.user.id, modal.where.value, modal.notes.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs finished: set to **Parked**.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "refresh_lock":
        # Guard (already checked above)
        async def do():
            return await service.refresh_squad_lock(ship["id"], interaction.user.id, days=2)
        ts = await with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message(f"Squad lock recorded until <t:{ts}:f>.", ephemeral=True)
        return

    if action == "notes_modal":
        modal = NotesModal(existing=ship.get("notes"))

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.set_notes(ship["id"], i.user.id, modal.notes.value)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Notes updated.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "switch_manage":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="manage"))
        return

    if action == "switch_info":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="info"))
        return

    if action == "switch_main":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        await interaction.response.edit_message(embed=ship_main_embed(fresh), view=ShipView(fresh, mode="main"))
        return

    # ---------- MANAGE actions ----------
    if action == "edit_modal":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        modal = EditModal(fresh)

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            dmg_txt = modal.damage.value.strip()
            dmg = max(0, min(5, int(dmg_txt))) if dmg_txt.isdigit() else 0
            fields = {
                "name": modal.name.value.strip(),
                "status": modal.status.value.strip(),
                "damage": dmg,
                "location": (modal.location.value or "").strip() or None,
                "keys": (modal.keys.value or "").strip() or None,
            }
            async def do():
                await i.client.service.edit_fields_bulk(ship["id"], i.user.id, fields)
            await with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Edited ship.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "log_modal":
        modal = LogModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.log_kill_and_op(ship["id"], i.user.id, modal.kills.value, modal.debrief.value)
            await with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("Logged.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "share_code":
        # Guard (already checked above)
        async def do():
            return await service.gen_one_time_share_code(ship["id"], interaction.user.id)
        code = await with_lock(f"ship:{ship['id']}", do)
        await interaction.response.send_message(
            f"One-time share code: **{code}** (consumed on first use).",
            ephemeral=True
        )
        return

    if action == "add_user_modal":
        modal = AddUserModal()

        async def on_submit(i: discord.Interaction):
            if not await require_ship_auth(i, ship["guild_id"], ship["name"]):
                return
            async def do():
                await service.add_ship_auth_user_text(ship["id"], modal.user.value, i.user.id)
            await with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("User authorized on this ship.", ephemeral=True)

        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "kill_confirm":
        # Simple confirm view
        class Confirm(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=30)

            @discord.ui.button(label="Confirm Kill", style=discord.ButtonStyle.danger)
            async def yes(self, ii: discord.Interaction, btn: discord.ui.Button):
                if not await require_ship_auth(ii, ship["guild_id"], ship["name"]):
                    return
                async def do():
                    await service.mark_dead(ship["id"], ii.user.id)
                await with_lock(f"ship:{ship['id']}", do)
                await _refresh_everywhere(ii.client, ship["id"])
                await ii.response.edit_message(content="Marked as **Dead** (read-only).", view=None)

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def no(self, ii: discord.Interaction, btn: discord.ui.Button):
                await ii.response.edit_message(content="Cancelled.", view=None)

        await interaction.response.send_message(
            "Confirm setting ship status to **Dead** (this makes it read-only).",
            view=Confirm(),
            ephemeral=True
        )
        return

    # ---------- INFO actions ----------
    if action == "show_actions":
        async with interaction.client.db.connect() as conn:
            cur = await conn.execute(
                """SELECT field, old_value, new_value, created_at, user_id
                   FROM ship_updates
                   WHERE ship_id=?
                   ORDER BY created_at DESC
                   LIMIT 25""",
                (ship["id"],)
            )
            rows = await cur.fetchall()

        if not rows:
            await interaction.response.send_message("No actions yet.", ephemeral=True)
            return

        def fmt(v):  # nice display for Nones/empties
            return "—" if v in (None, "") else str(v)

        lines = [f"• [{r[3]}] <@{r[4]}> {r[0]}: {fmt(r[1])} → {fmt(r[2])}" for r in rows]
        await interaction.response.send_message(safe_join_lines(lines), ephemeral=True)
        return

    if action == "show_kills":
        async with interaction.client.db.connect() as conn:
            cur = await conn.execute(
                "SELECT created_at, user_id, kills_raw "
                "FROM ship_kills "
                "WHERE ship_id=? "
                "ORDER BY created_at DESC LIMIT 10",
                (ship["id"],)
            )
            rows = await cur.fetchall()

        if not rows:
            await interaction.response.send_message("No kill logs.", ephemeral=True)
            return

        # Format lines safely and stay under 2000 chars
        lines = []
        for created_at, user_id, kills_raw in rows:
            text = (kills_raw or "").strip()
            if len(text) > 300:
                text = text[:297] + "…"
            lines.append(f"• [{created_at}] <@{user_id}>: {text}")

        await interaction.response.send_message(safe_join_lines(lines), ephemeral=True)
        return


    if action == "info_dump":
        import io
        import re

        async with interaction.client.db.connect() as conn:
            # ship row
            cur = await conn.execute("SELECT * FROM ships WHERE id=?", (ship["id"],))
            ship_row = await cur.fetchone()
            cols = [c[0] for c in cur.description]
            ship_map = dict(zip(cols, ship_row))

            # children
            cur = await conn.execute("SELECT * FROM ship_updates WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            logs = await cur.fetchall()

            cur = await conn.execute("SELECT * FROM ship_instances WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            inst = await cur.fetchall()

            cur = await conn.execute("SELECT * FROM ship_kills WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            kills = await cur.fetchall()

            cur = await conn.execute("SELECT * FROM ship_ops WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            ops = await cur.fetchall()

        # build a readable text dump
        lines = []
        lines.append("== SHIP ==")
        lines.append(repr(ship_map))
        lines.append("\n== LOGS ==")
        lines.extend(repr(r) for r in logs)
        lines.append("\n== INSTANCES ==")
        lines.extend(repr(r) for r in inst)
        lines.append("\n== KILLS ==")
        lines.extend(repr(r) for r in kills)
        lines.append("\n== OPS ==")
        lines.extend(repr(r) for r in ops)
        content = "\n".join(lines)

        # safe filename
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ship["name"] or "ship")
        buf = io.BytesIO(content.encode("utf-8"))
        file = discord.File(buf, filename=f"{safe_name}_info.txt")

        await interaction.response.send_message(file=file, ephemeral=True)
        return


# -----------------------------------------------------------------------------
# Ephemeral view for choosing ship type when creating
# -----------------------------------------------------------------------------
class AddShipTypeView(discord.ui.View):
    def __init__(self, cog, name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.name = name
        options = [
            discord.SelectOption(label="Longhook", value="Longhook"),
            discord.SelectOption(label="Bowhead", value="Bowhead"),
            discord.SelectOption(label="Destroyer", value="Destroyer"),
            discord.SelectOption(label="Submarine", value="Submarine"),
            discord.SelectOption(label="Bluefin", value="Bluefin"),
            discord.SelectOption(label="Battleship", value="Battleship"),
        ]
        self.add_item(ShipTypeSelect(self.cog, self.name, options))


class ShipTypeSelect(discord.ui.Select):
    def __init__(self, cog, name: str, options):
        super().__init__(placeholder="Select type…", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.ship_name = name

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        modal = CreateShipModal(self.cog, self.ship_name, selected_type)
        await interaction.response.send_modal(modal)
