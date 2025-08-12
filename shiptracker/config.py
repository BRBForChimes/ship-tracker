import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    token: str = os.getenv("DISCORD_TOKEN", "")
    database_path: str = os.getenv("DATABASE_PATH", "shiptracker.db")
    schema_path: str = os.getenv("SCHEMA_PATH", "shiptracker/db/schema.sql")
    war_number: int = int(os.getenv("WAR", "0"))

    # auth caches (seconds)
    auth_member_ttl: int = int(os.getenv("AUTH_MEMBER_TTL", "60"))
    auth_roles_map_ttl: int = int(os.getenv("AUTH_ROLES_MAP_TTL", "300"))
    auth_instance_guilds_ttl: int = int(os.getenv("AUTH_INST_GUILDS_TTL", "60"))
