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
      - [Windows](#windows)
      - [macOS](#macos)
      - [Debian/Ubuntu](#debianubuntu)
      - [Fedora-based](#fedora-based)
      - [Arch-based](#arch-based)
    - [First run](#first-run)
    - [Manual initialisation](#manual-initialisation)
    - [Getting a database connection](#getting-a-database-connection)
  - [Setting up multiple devices](#setting-up-multiple-devices)
    - [Prerequisite](#prerequisite)
      - [MACOS](#macos-1)
      - [Windows](#windows-1)
      - [Linux](#linux)
    - [Opening the site](#opening-the-site)
      - [1. using local IP (Only for server pc)](#1-using-local-ip-only-for-server-pc)
      - [2. using the IP you just found](#2-using-the-ip-you-just-found)
      - [3. Double cliking the HTML file](#3-double-cliking-the-html-file)
    - [Debugging](#debugging)
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
      - [`PUT /posts/{post_id}`](#put-postspost_id)
      - [`DELETE /posts/{post_id}`](#delete-postspost_id)
      - [`POST /likes/toggle`](#post-likestoggle)
      - [`POST /comments`](#post-comments)
      - [`DELETE /comments/{comment_id}`](#delete-commentscomment_id)
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

SQLite 3 · 4 tables (`users`, `posts`, `likes`, `comments`) · 8 indexes  
Managed by `database.py`: schema definition, `init_db()`, `get_conn()`.

---

## Schema

### `users`
| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER | PK AUTOINCREMENT |
| `username` | TEXT | NOT NULL UNIQUE |
| `email` | TEXT | UNIQUE |
| `bio` | TEXT | — |
| `profile_pic` | TEXT | URL |
| `timestamp` | TEXT | DEFAULT `datetime('now')` |

### `posts`
| Column | Type | Notes |
|---|---|---|
| `post_id` | INTEGER | PK AUTOINCREMENT |
| `user_id` | INTEGER | FK → `users` |
| `content` | TEXT | — |
| `image_urls` | TEXT | JSON array of image URLs |
| `timestamp` | TEXT | DEFAULT `datetime('now')` |
| `likes_count` | INTEGER | Denormalised counter (DEFAULT 0) |
| `updated_at` | TEXT | Set on edit |

### `likes`
| Column | Type | Notes |
|---|---|---|
| `user_id` | INTEGER | PK, FK → `users` |
| `post_id` | INTEGER | PK, FK → `posts` |
| `timestamp` | TEXT | DEFAULT `datetime('now')` |

Composite PK `(user_id, post_id)` prevents duplicate likes. Toggle logic: DELETE if exists, INSERT if not.

### `comments`
| Column | Type | Notes |
|---|---|---|
| `comment_id` | INTEGER | PK AUTOINCREMENT |
| `user_id` | INTEGER | FK → `users` |
| `post_id` | INTEGER | FK → `posts` |
| `parent_comment_id` | INTEGER | FK → `comments` (self-ref, NULL = top-level) |
| `content` | TEXT | NOT NULL |
| `timestamp` | TEXT | DEFAULT `datetime('now')` |

---

## Indexes

| Index | Table | Column(s) |
|---|---|---|
| `idx_users_username` | `users` | `username` |
| `idx_posts_user_id` | `posts` | `user_id` |
| `idx_posts_timestamp` | `posts` | `timestamp DESC` |
| `idx_posts_likes_count` | `posts` | `likes_count DESC` |
| `idx_posts_date` | `posts` | `DATE(timestamp)` |
| `idx_likes_post_id` | `likes` | `post_id` |
| `idx_comments_post_id` | `comments` | `post_id` |
| `idx_comments_parent` | `comments` | `parent_comment_id` |

---

## Entity-Relationship Diagram

```
┌───────────────┐     ┌──────────────────────┐
│     users     │     │        posts         │
│───────────────│     │──────────────────────│
│ user_id    PK │────►│ post_id           PK │
│ username      │     │ user_id           FK │
│ email         │     │ content              │
│ bio           │     │ image_urls  (JSON)   │
│ profile_pic   │     │ timestamp            │
│ timestamp     │     │ likes_count (derived)│
└───────┬───────┘     │ updated_at           │
        │             └──────────┬───────────┘
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
           │ parent_comment_id     FK │◄─┐ (self-ref)
           │ content                  │  │  parent_comment ──► replies_to ──► child_comment
           │ timestamp                │  │
           └──────────────────────────┘──┘
```

---

## Key Design Decisions

- **Denormalised `likes_count`** — avoids a `COUNT(*)` subquery on every feed request; updated atomically on each like toggle
- **Composite PK on `likes`** — enforces one-like-per-user-per-post at the DB level
- **Self-referencing FK on `comments`** — supports threaded replies without a separate table
- **`ON DELETE CASCADE`** — deleting a user/post/comment automatically cleans up all dependent rows
- **Idempotent `init_db()`** — safe to call on every startup; uses `CREATE TABLE IF NOT EXISTS`

---

## Database Files

| File | Description |
|---|---|
| `database.py` | Schema, `init_db()`, `get_conn()` |
| `social_app.db` | SQLite file (auto-created on first run) |
| `test_db.py` | Test & demo-data seeding script |

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

## Setting up multiple devices

### Prerequisite

Open port 8000 on your firewall on your server device, for me that would be
```bash
- sudo firewall-cmd --permanent --add-port=8000/tcp
- sudo firewall-cmd --reload
```
in the bash terminal, since I have firewalld running on linux.
Different OS have different ways, different firewalls, try to search for it.

In addition, on your server pc, find your local ip
In general, it looks something like 192.168.x.xxx

#### MACOS
```
ifconfig | grep "inet " | grep -v 127.0.0.1
```

#### Windows
Press windows + R, type cmd, enter.
```
ipconfig
```
Look for an IPv4 address

#### Linux
```bash
ip addr
```

### Opening the site
First, run 
```python
python app.py
```

There are 3 ways
#### 1. using local IP (Only for server pc)
in the browser, type
```
http://127.0.0.1:8000
```

#### 2. using the IP you just found
in the browser, type
```
http://YOUR_IP:8000
```
So for example, mine would be
```
http://192.168.1.114:8000
```

#### 3. Double cliking the HTML file
In your directory, double click the demo_app.html file
A window pops up
type in your IPv4 address

### Debugging
```bash
PING YOUR_SERVER_IP
```
Try to see if you get replies from the network connection

Another way to debug is via f12 menu in the browser, go to network tab and try to catch your IP there

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
| `CreatePost` | `username`, `content` (opt), `image_url` (opt), `image_urls` (opt) | `POST /posts` |
| `UpdatePost` | `username`, `content` (opt), `image_url` (opt), `image_urls` (opt) | `PUT /posts/{post_id}` |
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
Publish a new post (text and/or image) on behalf of an existing user. A post can
contain multiple image URLs by passing `image_urls`.

**Request body**
```json
{
  "username": "alice",
  "content": "Hello HKUgram!",
  "image_urls": [
    "https://example.com/photo-1.jpg",
    "https://example.com/photo-2.jpg"
  ]
}
```
**Response**
```json
{ "message": "Post published successfully" }
```
**Notes** — `image_url` is still accepted for backward compatibility and will be treated as the first image.
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
  "image_urls": [
    "https://example.com/new-photo-1.jpg",
    "https://example.com/new-photo-2.jpg"
  ]
}
```
**Response**
```json
{ "message": "Post updated successfully" }
```
**Notes** — `image_url` is still accepted for backward compatibility and will be treated as the first image.
**Error** — `400` if both `content` and the image list are empty.
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
