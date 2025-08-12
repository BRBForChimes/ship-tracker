# Ship Tracker Bot

Discord bot scaffold using discord.py Cogs + SQLite (append-only history).
- One DB file, per-war scoping via `.env` WAR number.
- No destructive deletes; all history retained.
- Cross-guild authorization (roles or users) with TTL caches.
- Sharing/instances table so you can update embeds everywhere.

## Quick start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
# edit .env: DISCORD_TOKEN and WAR
python bot.py
