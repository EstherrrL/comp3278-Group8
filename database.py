"""
database.py
HKUgram Group8 - Database initialisation module

Responsibilities:
  1. Define the full schema SQL (SCHEMA_SQL)
  2. Provide init_db()  - idempotent database initialisation and migration
  3. Provide get_conn() - return a connection with Row factory and FK enforcement
  4. Expose DB_PATH     - single source of truth for the database file path

Tables:
  users    - user accounts (username, optional email / bio / avatar)
  posts    - text and image posts with a denormalised like counter
  likes    - many-to-many like relationship; toggle logic lives in app.py
  comments - post comments and threaded replies via parent_comment_id
"""

import sqlite3
import os

# Database file path (resolved relative to this file's directory)
DB_PATH = os.path.join(os.path.dirname(__file__), "social_app.db")

# Schema: table definitions and indexes
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    email       TEXT    UNIQUE,          -- optional; allowed to be NULL in demo
    bio         TEXT,                    -- short personal bio
    profile_pic TEXT,                    -- avatar URL
    timestamp   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Posts table
CREATE TABLE IF NOT EXISTS posts (
    post_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    content     TEXT,
    image_url   TEXT,
    timestamp   TEXT    NOT NULL DEFAULT (datetime('now')),
    likes_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Likes table (many-to-many; toggle via INSERT OR IGNORE / DELETE in app.py)
CREATE TABLE IF NOT EXISTS likes (
    user_id   INTEGER NOT NULL,
    post_id   INTEGER NOT NULL,
    timestamp TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

-- Comments table (parent_comment_id = NULL means top-level; non-NULL means a reply)
CREATE TABLE IF NOT EXISTS comments (
    comment_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    post_id           INTEGER NOT NULL,
    parent_comment_id INTEGER,           -- NULL = top-level comment; non-NULL = reply
    content           TEXT    NOT NULL,
    timestamp         TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id)           REFERENCES users(user_id)       ON DELETE CASCADE,
    FOREIGN KEY (post_id)           REFERENCES posts(post_id)       ON DELETE CASCADE,
    FOREIGN KEY (parent_comment_id) REFERENCES comments(comment_id) ON DELETE CASCADE
);

-- Indexes for frequently used queries
CREATE INDEX IF NOT EXISTS idx_users_username    ON users(username);
CREATE INDEX IF NOT EXISTS idx_posts_user_id     ON posts(user_id);
CREATE INDEX IF NOT EXISTS idx_posts_timestamp   ON posts(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_posts_likes_count ON posts(likes_count DESC);
CREATE INDEX IF NOT EXISTS idx_likes_post_id     ON likes(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_post_id  ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent   ON comments(parent_comment_id);
"""


def get_conn() -> sqlite3.Connection:
    """Return a database connection with Row factory and foreign-key enforcement enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Idempotently initialise the database.

    Step 1 - migrate existing tables: add any columns that were introduced in
             later versions (ALTER TABLE wrapped in try/except because SQLite
             does not support IF NOT EXISTS for columns).
    Step 2 - run SCHEMA_SQL: CREATE TABLE IF NOT EXISTS statements and indexes.
    """
    conn = sqlite3.connect(DB_PATH)

    # Step 1: migrate legacy tables before running executescript,
    # so that foreign-key references to new columns are already valid.
    migrations = [
        # new columns for the users table
        "ALTER TABLE users ADD COLUMN email       TEXT UNIQUE",
        "ALTER TABLE users ADD COLUMN bio         TEXT",
        "ALTER TABLE users ADD COLUMN profile_pic TEXT",
        # new column for the comments table
        "ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            # column already exists or table does not exist yet - safe to ignore
            pass

    # Step 2: create tables and indexes (CREATE TABLE IF NOT EXISTS)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


# Automatically initialise the database when this module is imported
init_db()

