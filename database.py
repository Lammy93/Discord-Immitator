import sqlite3
import os
from datetime import datetime

DATABASE_FILE = os.getenv("DATABASE_PATH", "bot.db")

# Ensure the directory for the database file exists
db_dir = os.path.dirname(DATABASE_FILE)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db():
    """Initializes the database schema if it doesn't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Create table for sound bites
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS soundbites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                added_by TEXT NOT NULL,
                play_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create table for active imitation sessions (who is imitating whom)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS imitation_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, guild_id)
            )
        """)
        
        # Create table for member presets (saved copies)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS member_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preset_name TEXT NOT NULL,
                member_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(preset_name, user_id, guild_id)
            )
        """)
        conn.commit()

# --- Soundbites Methods ---

def add_soundbite(name: str, file_path: str, added_by: str) -> bool:
    """Adds a new sound bite to the database. Returns True if successful, False if exists."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO soundbites (name, file_path, added_by) VALUES (?, ?, ?)",
                (name.lower(), file_path, added_by)
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def get_soundbite(name: str):
    """Retrieves a sound bite record by its name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM soundbites WHERE name = ?", (name.lower(),))
        return cursor.fetchone()

def get_all_soundbites():
    """Retrieves all registered sound bites."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM soundbites ORDER BY name ASC")
        return cursor.fetchall()

def delete_soundbite(name: str) -> bool:
    """Deletes a sound bite by name. Returns True if deleted, False if not found."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM soundbites WHERE name = ?", (name.lower(),))
        conn.commit()
        return cursor.rowcount > 0

def increment_soundbite_count(name: str):
    """Increments the play count of a sound bite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE soundbites SET play_count = play_count + 1 WHERE name = ?", (name.lower(),))
        conn.commit()

# --- Imitation Sessions Methods ---

def start_imitation_session(user_id: str, target_id: str, guild_id: str):
    """Starts an imitation session where user_id imitates target_id in a guild."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO imitation_sessions (user_id, target_id, guild_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, guild_id) 
            DO UPDATE SET target_id = excluded.target_id
        """, (str(user_id), str(target_id), str(guild_id)))
        conn.commit()

def get_imitation_session(user_id: str, guild_id: str):
    """Retrieves the active imitation target for a specific user in a guild."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT target_id FROM imitation_sessions WHERE user_id = ? AND guild_id = ?",
            (str(user_id), str(guild_id))
        )
        row = cursor.fetchone()
        return row["target_id"] if row else None

def stop_imitation_session(user_id: str, guild_id: str) -> bool:
    """Stops an imitation session. Returns True if a session was ended."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM imitation_sessions WHERE user_id = ? AND guild_id = ?",
            (str(user_id), str(guild_id))
        )
        conn.commit()
        return cursor.rowcount > 0

def clear_all_sessions_for_guild(guild_id: str):
    """Clears all active imitation sessions in a guild (e.g. on bot startup or restart)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM imitation_sessions WHERE guild_id = ?", (str(guild_id),))
        conn.commit()

# --- Member Presets Methods ---

def add_member_preset(preset_name: str, member_id: str, guild_id: str, user_id: str) -> bool:
    """Saves a member as a named preset for a specific user. Returns True if successful."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO member_presets (preset_name, member_id, guild_id, user_id) VALUES (?, ?, ?, ?)",
                (preset_name.lower(), str(member_id), str(guild_id), str(user_id))
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False

def get_member_preset(preset_name: str, user_id: str, guild_id: str):
    """Retrieves a member ID for a specific preset name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT member_id FROM member_presets WHERE preset_name = ? AND user_id = ? AND guild_id = ?",
            (preset_name.lower(), str(user_id), str(guild_id))
        )
        row = cursor.fetchone()
        return row["member_id"] if row else None

def get_user_presets(user_id: str, guild_id: str):
    """Retrieves all presets saved by a user in a guild."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT preset_name, member_id FROM member_presets WHERE user_id = ? AND guild_id = ? ORDER BY preset_name ASC",
            (str(user_id), str(guild_id))
        )
        return cursor.fetchall()

def delete_member_preset(preset_name: str, user_id: str, guild_id: str) -> bool:
    """Deletes a specific preset. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM member_presets WHERE preset_name = ? AND user_id = ? AND guild_id = ?",
            (preset_name.lower(), str(user_id), str(guild_id))
        )
        conn.commit()
        return cursor.rowcount > 0

