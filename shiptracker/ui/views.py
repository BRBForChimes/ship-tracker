import time
import asyncio
import discord
from typing import Optional
from shiptracker.ui.embeds import ship_main_embed
from shiptracker.ui.modals import (
    ReturnModal, StartRepairsModal, FinishRepairsModal, NotesModal,
    EditModal, LogModal, AddUserModal
)
from shiptracker.utils.locks import locks

# custom-id: st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}
def make_cid(ship_id: int, war_id: int, mode: str, action: str) -> str:
    return f"st:ship:{ship_id}:war:{war_id}:mode:{mode}:act:{action}"

def parse_cid(custom_id: str) -> dict:
    parts = custom_id.split(":")
    try:
        return {"ship_id": int(parts[2]), "war_id": int(parts[4]), "mode": parts[6], "action": parts[8]}
    except Exception:
        return {"action": "invalid"}

def _status(ship: dict) -> str:
    return (ship.get("status") or "").strip()

class ShipView(discord.ui.View):
    def __init__(self, ship: dict, mode: str = "main"):
        super().__init__(timeout=None)
        self.ship_id = int(ship["id"])
        self.war_id = int(ship["war_id"])
        self.mode = mode
        self._build(ship)

    def _build(self, ship: dict):
        self.clear_items()
        status = _status(ship).lower()

        if self.mode == "main":
            # Depart / Return
            if status in {"repairing","deployed"}:
                label = "Return"
                act = "return_modal"
                style = discord.ButtonStyle.primary
            else:
                label = "Depart"
                act = "depart"
                style = discord.ButtonStyle.primary
            self.add_item(discord.ui.Button(label=label, style=style, custom_id=make_cid(self.ship_id, self.war_id, "main", act)))

            # Repair / Finish Repairs
            if status == "repairing":
                self.add_item(discord.ui.Button(label="Finish Repairs", style=discord.ButtonStyle.success,
                                                custom_id=make_cid(self.ship_id, self.war_id, "main", "finish_repairs_modal")))
            else:
                self.add_item(discord.ui.Button(label="Repair", style=discord.ButtonStyle.secondary,
                                                custom_id=make_cid(self.ship_id, self.war_id, "main", "start_repairs_modal")))

            # Refresh Squad Lock (clock)
            self.add_item(discord.ui.Button(emoji="⏰", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "main", "refresh_lock")))

            # Notes (notepad)
            self.add_item(discord.ui.Button(emoji="📝", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "main", "notes_modal")))

            # Manage / Info
            self.add_item(discord.ui.Button(label="Manage", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_manage")))
            self.add_item(discord.ui.Button(label="Info", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "main", "switch_info")))

        elif self.mode == "manage":
            self.add_item(discord.ui.Button(label="Edit", style=discord.ButtonStyle.primary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "edit_modal")))
            self.add_item(discord.ui.Button(label="Log", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "log_modal")))
            self.add_item(discord.ui.Button(emoji="🔗", label="Share", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "share_code")))
            self.add_item(discord.ui.Button(emoji="➕", label="Add User", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "add_user_modal")))
            self.add_item(discord.ui.Button(emoji="💀", label="Kill", style=discord.ButtonStyle.danger,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "kill_confirm")))
            self.add_item(discord.ui.Button(label="◀ Back", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "manage", "switch_main")))

        elif self.mode == "info":
            self.add_item(discord.ui.Button(label="Actions", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "info", "show_actions")))
            self.add_item(discord.ui.Button(label="Kill Log", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "info", "show_kills")))
            self.add_item(discord.ui.Button(label="Op Log", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "info", "show_ops")))
            self.add_item(discord.ui.Button(label="Info Dump", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "info", "info_dump")))
            self.add_item(discord.ui.Button(label="◀ Back", style=discord.ButtonStyle.secondary,
                                            custom_id=make_cid(self.ship_id, self.war_id, "info", "switch_main")))

async def _refresh_everywhere(client: discord.Client, ship_id: int):
    ship = await client.db.get_ship_by_id(ship_id)
    embed = ship_main_embed(ship)
    # Update this ship's tracked instances
    instances = await client.db.get_instances(ship_id)
    updated_channels = set()
    for inst in instances:
        try:
            ch = await client.fetch_channel(inst["channel_id"])
            if not hasattr(ch, "fetch_message"): continue
            msg = await ch.fetch_message(inst["message_id"])
            await msg.edit(embed=embed, view=ShipView(ship, mode="main"))
            updated_channels.add(inst["channel_id"])
        except Exception as e:
            logger = getattr(client, "logger", None)
            logger and logger.warning(f"Failed to update {inst}: {e}")

async def handle_component(interaction: discord.Interaction):
    if interaction.type is not discord.InteractionType.component:
        return
    data = interaction.data or {}
    cid = data.get("custom_id")
    if not cid or not cid.startswith("st:ship:"):
        return
    bits = parse_cid(cid)
    action = bits["action"]
    ship = await interaction.client.db.get_ship_by_id(bits["ship_id"])
    if not ship:
        await interaction.response.send_message("Ship not found.", ephemeral=True)
        return

    # Auth check (cross-guild by name)
    ok = await interaction.client.service_auth.user_is_authorized_for_ship_any_guild(
        ship["guild_id"], ship["name"], interaction.user.id
    )
    if not ok:
        await interaction.response.send_message("You’re not authorized for this ship.", ephemeral=True)
        return

    service = interaction.client.service

    # MAIN actions
    if action == "depart":
        async def do():
            await service.depart(ship["id"], interaction.user.id)
        await locks.with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message("Status set to **Deployed**.", ephemeral=True)
        return

    if action == "return_modal":
        modal = ReturnModal()
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.return_to_port(ship["id"], i.user.id, modal.where.value, modal.smokes.value, modal.notes.value)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Returned and updated.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "start_repairs_modal":
        modal = StartRepairsModal()
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.start_repairs(ship["id"], i.user.id, modal.where.value)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs started.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "finish_repairs_modal":
        modal = FinishRepairsModal()
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.finish_repairs(ship["id"], i.user.id, modal.where.value, modal.notes.value)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Repairs finished: set to **Parked**.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "refresh_lock":
        async def do():
            ts = await service.refresh_squad_lock(ship["id"], interaction.user.id, days=2)
            return ts
        ts = await locks.with_lock(f"ship:{ship['id']}", do)
        await _refresh_everywhere(interaction.client, ship["id"])
        await interaction.response.send_message(f"Squad lock recorded until <t:{ts}:f>.", ephemeral=True)
        return

    if action == "notes_modal":
        modal = NotesModal(existing=ship.get("notes"))
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.set_notes(ship["id"], i.user.id, modal.notes.value)
            await locks.with_lock(f"ship:{ship['id']}", do)
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

    # MANAGE actions
    if action == "edit_modal":
        fresh = await interaction.client.db.get_ship_by_id(ship["id"])
        modal = EditModal(fresh)
        async def on_submit(i: discord.Interaction):
            fields = {
                "name": modal.name.value.strip(),
                "status": modal.status.value.strip(),
                "damage": max(0, min(5, int(modal.damage.value))) if modal.damage.value.strip().isdigit() else 0,
                "location": (modal.location.value or "").strip() or None,
                "home_port": (modal.home_port.value or "").strip() or None,
                "regiment": (modal.regiment.value or "").strip() or None,
                "keys": (modal.keys.value or "").strip() or None,
            }
            async def do():
                await service.edit_fields_bulk(ship["id"], i.user.id, fields)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await _refresh_everywhere(i.client, ship["id"])
            await i.response.send_message("Edited ship fields.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "log_modal":
        modal = LogModal()
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.log_kill_and_op(ship["id"], i.user.id, modal.kills.value, modal.debrief.value)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("Logged.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "share_code":
        async def do():
            return await service.gen_one_time_share_code(ship["id"], interaction.user.id)
        code = await locks.with_lock(f"ship:{ship['id']}", do)
        await interaction.response.send_message(f"One-time share code: **{code}** (consumed on first use).", ephemeral=True)
        return

    if action == "add_user_modal":
        modal = AddUserModal()
        async def on_submit(i: discord.Interaction):
            async def do():
                await service.add_ship_auth_user_text(ship["id"], modal.user.value, i.user.id)
            await locks.with_lock(f"ship:{ship['id']}", do)
            await i.response.send_message("User authorized on this ship.", ephemeral=True)
        modal.on_submit = on_submit  # type: ignore
        await interaction.response.send_modal(modal)
        return

    if action == "kill_confirm":
        # simple confirm view
        class Confirm(discord.ui.View):
            def __init__(self): super().__init__(timeout=30)
            @discord.ui.button(label="Confirm Kill", style=discord.ButtonStyle.danger)
            async def yes(self, ii: discord.Interaction, btn: discord.ui.Button):
                async def do():
                    await service.mark_dead(ship["id"], ii.user.id)
                await locks.with_lock(f"ship:{ship['id']}", do)
                await _refresh_everywhere(ii.client, ship["id"])
                await ii.response.edit_message(content="Marked as **Dead** (read-only).", view=None)
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def no(self, ii: discord.Interaction, btn: discord.ui.Button):
                await ii.response.edit_message(content="Cancelled.", view=None)
        await interaction.response.send_message("Confirm setting ship status to **Dead** (this makes it read-only).", view=Confirm(), ephemeral=True)
        return

    # INFO actions
    if action == "show_actions":
        # last 25 updates
        logs = await interaction.client.db.connect().__aenter__()  # quick inline query
        async with interaction.client.db.connect() as conn:
            cur = await conn.execute(
                "SELECT field, old_value, new_value, created_at, user_id FROM ship_updates WHERE ship_id=? ORDER BY created_at DESC LIMIT 25",
                (ship["id"],)
            )
            rows = await cur.fetchall()
        if not rows:
            await interaction.response.send_message("No actions yet.", ephemeral=True); return
        lines = [f"• [{r[3]}] <@{r[4]}> {r[0]}: {r[1]} → {r[2]}" for r in rows]
        await interaction.response.send_message("\n".join(lines[:1800//2]), ephemeral=True)
        return

    if action == "show_kills":
        async with interaction.client.db.connect() as conn:
            cur = await conn.execute(
                "SELECT created_at, user_id, kills_raw FROM ship_kills WHERE ship_id=? ORDER BY created_at DESC LIMIT 10",
                (ship["id"],)
            )
            rows = await cur.fetchall()
        if not rows:
            await interaction.response.send_message("No kill logs.", ephemeral=True); return
        lines = [f"• [{r[0]}] <@{r[1]}>: {r[2]}" for r in rows]
        await interaction.response.send_message("\n".join(lines[:1800//2]), ephemeral=True)
        return

    if action == "show_ops":
        async with interaction.client.db.connect() as conn:
            cur = await conn.execute(
                "SELECT created_at, user_id, debrief FROM ship_ops WHERE ship_id=? ORDER BY created_at DESC LIMIT 10",
                (ship["id"],)
            )
            rows = await cur.fetchall()
        if not rows:
            await interaction.response.send_message("No operation logs.", ephemeral=True); return
        lines = [f"• [{r[0]}] <@{r[1]}>: {r[2]}" for r in rows]
        await interaction.response.send_message("\n".join(lines[:1800//2]), ephemeral=True)
        return

    if action == "info_dump":
        # Compose a text dump
        async with interaction.client.db.connect() as conn:
            # ship row
            cur = await conn.execute("SELECT * FROM ships WHERE id=?", (ship["id"],))
            ship_row = await cur.fetchone()
            cols = [c[0] for c in cur.description]
            ship_map = dict(zip(cols, ship_row))

            # children
            def grab(q, args=()):
                return conn.execute(q, args)

            cur = await conn.execute("SELECT * FROM ship_logs WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            logs = await cur.fetchall()
            cur = await conn.execute("SELECT * FROM ship_instances WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            inst = await cur.fetchall()
            cur = await conn.execute("SELECT * FROM ship_kills WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            kills = await cur.fetchall()
            cur = await conn.execute("SELECT * FROM ship_ops WHERE ship_id=? ORDER BY created_at", (ship["id"],))
            ops = await cur.fetchall()

        dump_lines = [
            "== SHIP ==",
            repr(ship_map),
            "\n== LOGS ==",
            *(repr(r) for r in logs),
            "\n== INSTANCES ==",
            *(repr(r) for r in inst),
            "\n== KILLS ==",
            *(repr(r) for r in kills),
            "\n== OPS ==",
            *(repr(r) for r in ops),
        ]
        content = "\n".join(dump_lines)
        f = discord.File(fp=discord.utils._from_json({"content": content}), filename=f"{ship['name']}_info.txt")  # quick in-memory
        # simpler: use io.StringIO
        import io
        f = discord.File(io.BytesIO(content.encode("utf-8")), filename=f"{ship['name']}_info.txt")
        await interaction.response.send_message(file=f, ephemeral=True)
        return
