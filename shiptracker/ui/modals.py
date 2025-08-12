import discord

class ReturnModal(discord.ui.Modal, title="Return to Port"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(label="Where is the ship?", required=True, max_length=100)
        self.smokes = discord.ui.TextInput(label="How many smokes? (0–5)", required=False, max_length=2)
        self.notes = discord.ui.TextInput(label="Any additional notes? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
        self.add_item(self.where); self.add_item(self.smokes); self.add_item(self.notes)

class StartRepairsModal(discord.ui.Modal, title="Start Repairs"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(label="Where is the drydock located?", required=True, max_length=100)
        self.add_item(self.where)

class FinishRepairsModal(discord.ui.Modal, title="Finish Repairs"):
    def __init__(self):
        super().__init__()
        self.where = discord.ui.TextInput(label="Where is the ship parked?", required=True, max_length=100)
        self.notes = discord.ui.TextInput(label="Any additional notes? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
        self.add_item(self.where); self.add_item(self.notes)

class NotesModal(discord.ui.Modal, title="Edit Notes"):
    def __init__(self, existing: str | None = None):
        super().__init__()
        self.notes = discord.ui.TextInput(label="Notes (empty to clear)", style=discord.TextStyle.paragraph, required=False, max_length=1000, default=existing or "")
        self.add_item(self.notes)

class EditModal(discord.ui.Modal, title="Edit Ship"):
    def __init__(self, ship: dict):
        super().__init__()
        self.name = discord.ui.TextInput(label="Name", default=ship.get("name",""), max_length=64)
        self.status = discord.ui.TextInput(label="Status", default=ship.get("status",""), max_length=32)
        self.damage = discord.ui.TextInput(label="Damage (0–5)", default=str(ship.get("damage") or 0), max_length=2, required=False)
        self.location = discord.ui.TextInput(label="Location", default=ship.get("location","") or "", max_length=100, required=False)
        self.home_port = discord.ui.TextInput(label="Home Port", default=ship.get("home_port","") or "", max_length=100, required=False)
        self.regiment = discord.ui.TextInput(label="Regiment", default=ship.get("regiment","") or "", max_length=100, required=False)
        self.keys = discord.ui.TextInput(label="Keys", default=ship.get("keys","") or "", max_length=200, required=False)
        for item in (self.name,self.status,self.damage,self.location,self.home_port,self.regiment,self.keys):
            self.add_item(item)

class LogModal(discord.ui.Modal, title="Log Actions"):
    def __init__(self):
        super().__init__()
        self.kills = discord.ui.TextInput(label="Kill Log (optional)", required=False, max_length=1000)
        self.debrief = discord.ui.TextInput(label="Action Report (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1500)
        self.add_item(self.kills); self.add_item(self.debrief)

class AddUserModal(discord.ui.Modal, title="Authorise User on this Ship"):
    def __init__(self):
        super().__init__()
        self.user = discord.ui.TextInput(label="User mention or ID", required=True, max_length=64)
        self.add_item(self.user)
