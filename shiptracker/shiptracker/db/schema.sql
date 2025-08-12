PRAGMA foreign_keys = ON;

-- Wars: global numeric ID (e.g., 125)
CREATE TABLE IF NOT EXISTS wars (
  id          INTEGER PRIMARY KEY,              -- set from .env WAR, e.g., 125
  started_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  ended_at    TEXT
);

-- Guild-level auth config
CREATE TABLE IF NOT EXISTS guild_auth_roles (
  guild_id    INTEGER NOT NULL,
  role_id     INTEGER NOT NULL,
  PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS guild_auth_users (
  guild_id    INTEGER NOT NULL,
  user_id     INTEGER NOT NULL,
  PRIMARY KEY (guild_id, user_id)
);

-- Ships (append-only; scope fixed after insert)
CREATE TABLE IF NOT EXISTS ships (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id           INTEGER NOT NULL,
  war_id             INTEGER NOT NULL,
  type               TEXT,
  name               TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'Parked',
  damage             INTEGER NOT NULL DEFAULT 0,         -- clamped 0–5
  location           TEXT,
  home_port          TEXT,
  notes              TEXT,
  squad_lock_until   INTEGER NOT NULL DEFAULT 0,         -- unix ts; 0 = unset
  keys               TEXT,
  image_url          TEXT,
  regiment           TEXT,
  share_code         TEXT,
  created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at         TEXT DEFAULT CURRENT_TIMESTAMP,
  link_root_id     INTEGER,
  UNIQUE (guild_id, war_id, name),
  FOREIGN KEY (war_id) REFERENCES wars(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_ships_link_root ON ships(link_root_id);

-- Flexible supplies
CREATE TABLE IF NOT EXISTS ship_supplies (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ship_id     INTEGER NOT NULL,
  resource    TEXT NOT NULL,
  quantity    INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (ship_id, resource),
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
);

-- Message instances for updating shared embeds
CREATE TABLE IF NOT EXISTS ship_instances (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ship_id     INTEGER NOT NULL,
  guild_id    INTEGER NOT NULL,
  channel_id  INTEGER NOT NULL,
  message_id  INTEGER NOT NULL,
  is_original INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (guild_id, channel_id, message_id),
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE,
  CHECK (is_original IN (0,1))
);

-- Kills
CREATE TABLE IF NOT EXISTS ship_kills (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ship_id     INTEGER NOT NULL,
  user_id     INTEGER,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  kills_raw   TEXT NOT NULL,
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
);

-- Operation debriefs
CREATE TABLE IF NOT EXISTS ship_ops (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ship_id     INTEGER NOT NULL,
  user_id     INTEGER,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  debrief     TEXT NOT NULL,
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
);

-- Per-ship extra authorized users
CREATE TABLE IF NOT EXISTS ship_auth_users (
  ship_id     INTEGER NOT NULL,
  user_id     INTEGER NOT NULL,
  authed_by   INTEGER,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ship_id, user_id),
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
);

-- Update history (used for "Actions")
CREATE TABLE IF NOT EXISTS ship_updates (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ship_id     INTEGER NOT NULL,
  user_id     INTEGER NOT NULL,
  field       TEXT NOT NULL,
  old_value   TEXT,
  new_value   TEXT,
  created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ship_id) REFERENCES ships(id) ON DELETE CASCADE
);

-- Indexes (removed ship_logs index; it’s not used)
CREATE INDEX IF NOT EXISTS idx_ships_scope           ON ships(guild_id, war_id, name);
CREATE INDEX IF NOT EXISTS idx_instances_ship        ON ship_instances(ship_id);
CREATE INDEX IF NOT EXISTS idx_kills_ship_time       ON ship_kills(ship_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ops_ship_time         ON ship_ops(ship_id, created_at);
CREATE INDEX IF NOT EXISTS idx_updates_ship_time     ON ship_updates(ship_id, created_at);

-- Touch updated_at on any ship update
CREATE TRIGGER IF NOT EXISTS ships_touch AFTER UPDATE ON ships
BEGIN
  UPDATE ships SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Forbid deletes (archive-only) at the "root" tables
CREATE TRIGGER IF NOT EXISTS prevent_delete_wars
BEFORE DELETE ON wars
BEGIN
  SELECT RAISE(ABORT, 'Deleting wars is disabled (archive-only).');
END;

CREATE TRIGGER IF NOT EXISTS prevent_delete_ships
BEFORE DELETE ON ships
BEGIN
  SELECT RAISE(ABORT, 'Deleting ships is disabled (archive-only).');
END;

-- Prevent changing scope fields
CREATE TRIGGER IF NOT EXISTS prevent_scope_update_on_ships
BEFORE UPDATE OF guild_id, war_id ON ships
BEGIN
  SELECT RAISE(ABORT, 'Cannot change guild_id/war_id of an existing ship.');
END;
