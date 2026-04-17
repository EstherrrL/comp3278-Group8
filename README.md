# comp3278-Group8

A simple social media web application built for COMP3278 Group 8.  
This document covers the **database layer** and the **backend API** of the project.

---

## Table of Contents

- [comp3278-Group8](#comp3278-group8)
  - [Table of Contents](#table-of-contents)
  - [Project Structure](#project-structure)
  - [Database Overview](#database-overview)
  - [Schema](#schema)
    - [`users`](#users)
    - [`posts`](#posts)
    - [`likes`](#likes)
    - [`comments`](#comments)
  - [Indexes](#indexes)
  - [Entity-Relationship Diagram](#entity-relationship-diagram)
  - [Key Design Decisions](#key-design-decisions)
  - [Database Files](#database-files)
  - [Setup \& Usage](#setup--usage)
    - [Prerequisites](#prerequisites)
    - [First run](#first-run)
    - [Manual initialisation](#manual-initialisation)
    - [Getting a database connection](#getting-a-database-connection)
  - [Running Tests](#running-tests)
    - [Demo mode — reset \& seed data](#demo-mode--reset--seed-data)
    - [Check mode — validate existing data only](#check-mode--validate-existing-data-only)
    - [Test coverage](#test-coverage)
  - [Backend API — `app.py`](#backend-api--apppy)
    - [Overview](#overview)
    - [Environment Variables](#environment-variables)
    - [Pydantic Request Models](#pydantic-request-models)
    - [API Endpoints](#api-endpoints)
      - [`POST /users`](#post-users)
      - [`POST /posts`](#post-posts)
      - [`POST /likes/toggle`](#post-likestoggle)
      - [`POST /comments`](#post-comments)
      - [`GET /feed?sort=time&limit=20`](#get-feedsorttimelimit20)
      - [`GET /users/{username}/posts`](#get-usersusernameposts)
      - [`GET /posts/{post_id}/comments`](#get-postspost_idcomments)
      - [`POST /chat` *(Vanna AI)*](#post-chat-vanna-ai)
    - [Vanna AI Integration](#vanna-ai-integration)
    - [Starting the Server](#starting-the-server)

---

## Project Structure

```
comp3278-Group8/
├── app.py               # FastAPI backend (business logic & API routes)
├── database.py          # Database module: schema, init_db(), get_conn()
├── test_db.py           # Database test & demo-data seeding script
├── social_app.db        # SQLite database file (auto-generated)
├── demo_social_app.py   # Minimal demo version of the app
├── demo_index.html      # Frontend UI (Tailwind CSS + vanilla JS)
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Database Overview

| Item | Value |
|---|---|
| Engine | SQLite 3 |
| File | `social_app.db` |
| Module | `database.py` |
| Foreign Keys | Enabled (`PRAGMA foreign_keys = ON`) |
| Tables | 4 (`users`, `posts`, `likes`, `comments`) |
| Indexes | 7 |

The database module (`database.py`) is responsible for:

1. Defining the full schema (`SCHEMA_SQL`)
2. `init_db()` — idempotent initialisation & automatic migration of existing databases
3. `get_conn()` — returns a connection with `Row` factory and foreign-key enforcement enabled
4. Exposing `DB_PATH` so that `app.py` and `test_db.py` share a single source of truth

---

## Schema

### `users`

Stores registered user accounts.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique user identifier |
| `username` | TEXT | NOT NULL UNIQUE | Display name (used in all API calls) |
| `email` | TEXT | UNIQUE | Optional email address |
| `bio` | TEXT | — | Short personal bio |
| `profile_pic` | TEXT | — | URL of the user's avatar image |
| `timestamp` | TEXT | NOT NULL DEFAULT `datetime('now')` | Account creation time |

---

### `posts`

Stores text and/or image posts created by users.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `post_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique post identifier |
| `user_id` | INTEGER | NOT NULL, FK → `users.user_id` | Author of the post |
| `content` | TEXT | — | Text body of the post |
| `image_url` | TEXT | — | Optional image URL |
| `timestamp` | TEXT | NOT NULL DEFAULT `datetime('now')` | Post creation time |
| `likes_count` | INTEGER | NOT NULL DEFAULT 0 | Denormalised like count for fast feed sorting |

> **Why denormalise `likes_count`?**  
> Sorting a large feed by popularity requires counting likes per post on every request. Maintaining a counter column keeps the `ORDER BY likes_count DESC` query O(1) per row, at the cost of two extra writes per toggle-like operation.

---

### `likes`

Many-to-many relationship between users and posts (toggle like / unlike).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `user_id` | INTEGER | NOT NULL, PK, FK → `users.user_id` | User who liked the post |
| `post_id` | INTEGER | NOT NULL, PK, FK → `posts.post_id` | Post that was liked |
| `timestamp` | TEXT | NOT NULL DEFAULT `datetime('now')` | Time of the like action |

- The composite primary key `(user_id, post_id)` prevents duplicate likes.
- **Toggle logic** (in `app.py`): check existence → `DELETE` if present, `INSERT` if absent; update `posts.likes_count` accordingly.

---

### `comments`

Stores top-level comments and threaded replies on posts.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `comment_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique comment identifier |
| `user_id` | INTEGER | NOT NULL, FK → `users.user_id` | Author of the comment |
| `post_id` | INTEGER | NOT NULL, FK → `posts.post_id` | Post being commented on |
| `parent_comment_id` | INTEGER | FK → `comments.comment_id` | `NULL` = top-level comment; non-`NULL` = reply |
| `content` | TEXT | NOT NULL | Comment text |
| `timestamp` | TEXT | NOT NULL DEFAULT `datetime('now')` | Comment creation time |

- Setting `parent_comment_id = NULL` creates a top-level comment.
- Setting `parent_comment_id = <id>` creates a reply to that comment (one level of nesting is sufficient for the current UI).
- `ON DELETE CASCADE` on the foreign key means deleting a parent comment also removes all its replies.

---

## Indexes

| Index Name | Table | Column(s) | Purpose |
|---|---|---|---|
| `idx_users_username` | `users` | `username` | Fast user look-up by username |
| `idx_posts_user_id` | `posts` | `user_id` | Fetch all posts by a specific user |
| `idx_posts_timestamp` | `posts` | `timestamp DESC` | Chronological feed (`ORDER BY timestamp DESC`) |
| `idx_posts_likes_count` | `posts` | `likes_count DESC` | Popularity feed (`ORDER BY likes_count DESC`) |
| `idx_likes_post_id` | `likes` | `post_id` | Count / list users who liked a post |
| `idx_comments_post_id` | `comments` | `post_id` | Fetch all comments for a post |
| `idx_comments_parent` | `comments` | `parent_comment_id` | Fetch replies to a specific comment |

---

## Entity-Relationship Diagram

```
┌───────────────┐     ┌──────────────────────┐
│     users     │     │        posts         │
│───────────────│     │──────────────────────│
│ user_id    PK │────►│ post_id           PK │
│ username      │     │ user_id           FK │
│ email         │     │ content              │
│ bio           │     │ image_url            │
│ profile_pic   │     │ timestamp            │
│ timestamp     │     │ likes_count          │
└───────┬───────┘     └──────────┬───────────┘
        │                        │
        │  ┌──────────────────┐  │
        │  │      likes       │  │
        │  │──────────────────│  │
        ├─►│ user_id    PK,FK │  │
        │  │ post_id    PK,FK │◄─┘
        │  │ timestamp        │
        │  └──────────────────┘
        │
        │  ┌──────────────────────────┐
        │  │         comments         │
        │  │──────────────────────────│
        │  │ comment_id            PK │
        └─►│ user_id               FK │
           │ post_id               FK │◄── posts
           │ parent_comment_id     FK │◄─┐
           │ content                  │  │ (self-ref)
           │ timestamp                │  │
           └──────────────────────────┘──┘
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **SQLite** | Zero-config, file-based; ideal for a course demo with no production deployment requirement |
| **Denormalised `likes_count`** | Avoids a `COUNT(*)` subquery on every feed request; counter is updated atomically within the toggle-like transaction |
| **Composite PK on `likes`** | Enforces the one-like-per-user-per-post constraint at the database level, not just application level |
| **Self-referencing FK on `comments`** | Supports threaded replies without adding a separate `replies` table |
| **`ON DELETE CASCADE` everywhere** | Deleting a user automatically removes all their posts, likes, and comments, keeping referential integrity without manual cleanup |
| **Idempotent `init_db()`** | Uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE` wrapped in `try/except`; safe to call on startup even when the database already exists or was created by an older version |

---

## Database Files

| File | Description |
|---|---|
| `database.py` | Schema definition, `init_db()`, `get_conn()`, `DB_PATH` constant |
| `social_app.db` | SQLite binary database file (auto-created on first run) |
| `test_db.py` | Test & demo-data seeding script (see below) |

---

## Setup & Usage

### Prerequisites

**Install Python & pip** if not already available:

#### Windows
```
powershell
# Download Python from https://python.org (installer includes pip)
# Verify installation
python --version
pip --version
```bash
pip install -r requirements.txt
```

#### macOS
```
# Using Homebrew
brew install python

# Verify installation
python3 --version
pip3 --version
```
#### Debian/Ubuntu
```
sudo apt update
sudo apt install python3 python3-pip
```
#### Fedora-based
```
sudo dnf install python3 python3-pip
```

#### Arch-based
```
sudo pacman -S python python-pip
```
### First run

The database is initialised automatically when `database.py` is imported (the last line calls `init_db()`).  
Starting the API server is sufficient:

```bash
python app.py
# or
uvicorn app:app --reload
```


### Manual initialisation

```python
from database import init_db
init_db()   # idempotent — safe to call multiple times
```

### Getting a database connection

```python
from database import get_conn

conn = get_conn()
rows = conn.execute("SELECT * FROM posts ORDER BY likes_count DESC LIMIT 10").fetchall()
for row in rows:
    print(dict(row))
conn.close()
```

---

## Running Tests

`test_db.py` provides two modes:

### Demo mode — reset & seed data

Drops and recreates `social_app.db`, then inserts 5 users, 8 posts, 14 like relationships, and 8 comments (including threaded replies). Use this only when you explicitly want to reset the database before a live demo.

```bash
python test_db.py --reset
```

### Check mode — validate existing data only

Runs the feed, user-history, and cascade-delete checks against the current database without modifying it.

```bash
python test_db.py
python test_db.py --check
```

Running `python test_db.py` without flags is now safe by default and will not delete previously registered users or posts.

### Test coverage

| # | Test | What is verified |
|---|---|---|
| 1 | User creation | Row count, `email`, `bio` fields |
| 2 | Post creation | Row count |
| 3 | Toggle like | `likes_count` increments, decrements, and re-increments correctly |
| 4 | Comments & replies | Total count, threaded structure via `parent_comment_id` |
| 5 | Feed queries | Chronological and popularity ordering |
| 6 | User history | Filtering posts by username |
| 7 | Cascade delete | Removing a user also removes all related posts, likes, and comments |

---

## Backend API — `app.py`

### Overview

`app.py` is the FastAPI application server. It imports the database module for
all data access and integrates the **Vanna AI** agent to support natural-language
queries against the SQLite database.

| Item | Value |
|---|---|
| Framework | FastAPI |
| Server | Uvicorn |
| Default port | `8000` |
| Interactive docs | `http://127.0.0.1:8000/docs` |
| AI chat endpoint | `POST /chat` (provided by Vanna) |
| CORS | All origins allowed (`*`) |

---

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | API key for the DeepSeek LLM (used by Vanna) |

Set it before starting the server:

```bash
export DEEPSEEK_API_KEY=your_key_here
python app.py
```

---

### Pydantic Request Models

| Model | Fields | Used by |
|---|---|---|
| `CreateUser` | `username: str` | `POST /users` |
| `CreatePost` | `username`, `content` (opt), `image_url` (opt) | `POST /posts` |
| `UpdatePost` | `username`, `content` (opt), `image_url` (opt) | `PUT /posts/{post_id}` |
| `ToggleLike` | `username`, `post_id: int` | `POST /likes/toggle` |
| `CreateComment` | `username`, `post_id`, `content`, `parent_comment_id` (opt) | `POST /comments` |
| `DeletePost` | `username` | `DELETE /posts/{post_id}` |

---

### API Endpoints

#### `POST /users`
Create a new user. Usernames must be unique.

**Request body**
```json
{ "username": "alice" }
```
**Response**
```json
{ "message": "User created successfully" }
```

**Error** — `409` if the username already exists.

---

#### `POST /posts`
Publish a new post (text and/or image) on behalf of an existing user.

**Request body**
```json
{
  "username": "alice",
  "content": "Hello HKUgram!",
  "image_url": "https://example.com/photo.jpg"
}
```
**Response**
```json
{ "message": "Post published successfully" }
```
**Error** — `404` if the username does not exist.

---

#### `PUT /posts/{post_id}`
Overwrite the content and/or image URL of an existing post. Only the original author
is allowed to edit the post.

**Request body**
```json
{
  "username": "alice",
  "content": "Edited text",
  "image_url": "https://example.com/new-photo.jpg"
}
```
**Response**
```json
{ "message": "Post updated successfully" }
```
**Error** — `400` if both `content` and `image_url` are empty.
**Error** — `403` if the user tries to edit someone else's post.
**Error** — `404` if the user or post does not exist.

---

#### `DELETE /posts/{post_id}`
Delete an existing post. Only the original author is allowed to delete it.

**Request body**
```json
{ "username": "alice" }
```
**Response**
```json
{ "message": "Post deleted successfully" }
```
**Error** — `403` if the user tries to delete someone else's post.
**Error** — `404` if the user or post does not exist.

---

#### `POST /likes/toggle`
Toggle a like on a post. Liking an already-liked post cancels the like.  
Updates `posts.likes_count` atomically in the same transaction.

**Request body**
```json
{ "username": "bob", "post_id": 3 }
```
**Response**
```json
{ "message": "Like toggled successfully" }
```
**Error** — `404` if the username does not exist.

---

#### `POST /comments`
Add a top-level comment or a threaded reply to a post.  
Set `parent_comment_id` to the `comment_id` of the parent to create a reply;
omit it (or set it to `null`) for a top-level comment.

**Request body**
```json
{
  "username": "carol",
  "post_id": 1,
  "content": "Great post!",
  "parent_comment_id": null
}
```
**Response**
```json
{ "message": "Comment added successfully" }
```
**Error** — `404` if the username does not exist.

---

#### `DELETE /comments/{comment_id}`
Delete one of the current user's own comments. Replies are also deleted automatically
if the removed comment is a parent comment, because the database foreign key uses
`ON DELETE CASCADE`.

**Request body**
```json
{ "username": "carol" }
```
**Response**
```json
{ "message": "Comment deleted successfully" }
```
**Error** — `404` if the username or comment does not exist.
**Error** — `403` if the user tries to delete someone else's comment.

---

#### `GET /feed?sort=time&limit=20`
Return a list of posts sorted by time (default) or popularity.

| Query param | Type | Default | Values |
|---|---|---|---|
| `sort` | string | `"time"` | `"time"` (newest first) \| `"popularity"` (most liked first) |
| `limit` | int | `20` | Any positive integer |

**Response** — array of post objects:
```json
[
  {
    "id": 1,
    "username": "alice",
    "text_content": "Hello HKUgram!",
    "image_url": null,
    "created_at": "2026-04-13 10:00:00",
    "like_count": 5
  }
]
```

---

#### `GET /users/{username}/posts`
Return all posts by a specific user, newest first.

**Response** — same structure as `/feed` but without `username` field.

**Error** — empty array `[]` if the user has no posts (no 404).

---

#### `GET /posts/{post_id}/comments`
Return all comments for a post in chronological order.

**Response**
```json
[
  {
    "comment_id": 1,
    "username": "bob",
    "content": "Nice one!",
    "timestamp": "2026-04-13 10:05:00",
    "parent_comment_id": null
  },
  {
    "comment_id": 2,
    "username": "carol",
    "content": "Agreed!",
    "timestamp": "2026-04-13 10:06:00",
    "parent_comment_id": 1
  }
]
```

---

#### `POST /chat` *(Vanna AI)*
Send a natural-language question about the database. The Vanna agent translates
it into SQL, runs it against `social_app.db`, and returns the result.

**Request body**
```json
{ "question": "Which user has the most likes in total?", "stream": false }
```
**Response**
```json
{ "response": "alice (12 likes)" }
```

---

### Vanna AI Integration

Vanna is configured in `app.py` with the following components:

| Component | Implementation |
|---|---|
| LLM | DeepSeek (`deepseek-chat`) via `OpenAILlmService` |
| SQL runner | `SqliteRunner` pointing at `social_app.db` |
| Tools | `RunSqlTool`, `VisualizeDataTool` |
| Memory | `DemoAgentMemory` (in-memory, up to 1 000 items) |
| User resolver | `SimpleUserResolver` — all requests run as `student@hku.hk` |
| Max iterations | 50 tool calls per chat turn |

---

### Starting the Server

```bash
# Option 1 — run directly
python app.py

# Option 2 — uvicorn with auto-reload (development)
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Once running, open:
- **`http://127.0.0.1:8000/docs`** — Swagger UI to test all endpoints interactively
- **`demo_index.html`** — full frontend UI (feed, like, comment, Vanna chat box)
