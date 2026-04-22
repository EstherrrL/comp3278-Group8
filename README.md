# comp3278-Group8

HKUgram — a simple social media web app built for COMP3278 Group 8.  
Stack: **FastAPI** · **SQLite** · **Tailwind CSS** · **Vanna AI**

---

## Table of Contents

- [Project Structure](#project-structure)
- [Database](#database)
- [Entity-Relationship Diagram](#entity-relationship-diagram)
- [UI Design](#ui-design)
- [Features & Functions](#features--functions)
- [API Endpoints](#api-endpoints)
- [Vanna AI Integration](#vanna-ai-integration)
- [Setup & Usage](#setup--usage)
- [Multi-device Access](#multi-device-access)
- [Running Tests](#running-tests)

---

## Project Structure

```
comp3278-Group8/
├── app.py            # FastAPI backend
├── database.py       # Schema, init_db(), get_conn()
├── demo_index.html   # Frontend UI (Tailwind CSS + vanilla JS)
├── test_db.py        # Test & demo-data seeder
├── social_app.db     # SQLite database (auto-generated)
├── requirements.txt
└── README.md
```

---

## Database

SQLite 3 · 4 tables · 8 indexes · managed by `database.py`

### Schema

| Table | Key Columns |
|---|---|
| **users** | `user_id` PK, `username` UNIQUE, `email`, `bio`, `profile_pic`, `timestamp` |
| **posts** | `post_id` PK, `user_id` FK, `content`, `image_urls` (JSON), `likes_count`, `updated_at`, `timestamp` |
| **likes** | `(user_id, post_id)` composite PK — prevents duplicate likes |
| **comments** | `comment_id` PK, `user_id` FK, `post_id` FK, `parent_comment_id` FK (self-ref for replies), `content`, `timestamp` |

### Design Notes

- **`likes_count` denormalised** — avoids `COUNT(*)` on every feed query; updated atomically per toggle
- **Self-referencing FK on `comments`** — threaded replies without an extra table
- **`ON DELETE CASCADE`** — removing a user/post cascades to all related rows
- **Idempotent `init_db()`** — safe to call on every startup

### Indexes

`idx_users_username` · `idx_posts_user_id` · `idx_posts_timestamp DESC` · `idx_posts_likes_count DESC` · `idx_posts_date` · `idx_likes_post_id` · `idx_comments_post_id` · `idx_comments_parent`

---

## Entity-Relationship Diagram

```
┌───────────────┐         ┌──────────────────────┐
│     users     │         │        posts         │
│───────────────│         │──────────────────────│
│ user_id    PK │────────►│ post_id           PK │
│ username      │         │ user_id           FK │
│ email         │         │ content              │
│ bio           │         │ image_urls  (JSON)   │
│ profile_pic   │         │ timestamp            │
│ timestamp     │         │ likes_count (derived)│
└───────┬───────┘         │ updated_at           │
        │                 └──────────┬───────────┘
        │   ┌──────────────────┐     │
        │   │      likes       │     │
        │   │──────────────────│     │
        ├──►│ user_id    PK,FK │     │
        │   │ post_id    PK,FK │◄────┘
        │   │ timestamp        │
        │   └──────────────────┘
        │   ┌─────────────────────────────┐
        │   │          comments           │
        │   │─────────────────────────────│
        │   │ comment_id              PK  │
        └──►│ user_id                 FK  │
            │ post_id                 FK  │◄── posts
            │ parent_comment_id       FK  │◄─┐ (self-ref)
            │ content                     │  │  parent_comment ──► replies_to ──► child_comment
            │ timestamp                   │  │
            └─────────────────────────────┘──┘
```

---

## UI Design

Frontend is a single-page HTML file (`demo_index.html`) built with **Tailwind CSS** and vanilla JavaScript. No build step required — open directly in a browser or serve via FastAPI.

### Layout

| Section | Description |
|---|---|
| **Navbar** | App title, username input to switch accounts |
| **Feed** | Scrollable post cards sorted by time or popularity |
| **Post Card** | Author, content, image(s), like button with count, comment count, edit/delete (own posts) |
| **Comment Panel** | Expandable per post; supports threaded replies |
| **Create Post** | Text + multi-image upload (drag & drop supported) |
| **AI Chat Box** | Floating chat widget — send natural language queries to Vanna AI |

### Tech Choices

- **Tailwind CSS** (CDN) — utility-first styling, no build pipeline
- **Vanilla JS** — `fetch` API for all backend calls, no framework dependency
- **Multi-image preview** — `FileReader` API renders thumbnails before upload

---

## Features & Functions

| Feature | Implementation |
|---|---|
| User registration | `POST /users` — unique username required |
| Create post | `POST /posts` — text + multi-image (JSON `image_urls`) |
| Edit post | `PUT /posts/{post_id}` — author-only |
| Delete post | `DELETE /posts/{post_id}` — author-only, cascades comments & likes |
| Toggle like | `POST /likes/toggle` — like/unlike, updates `likes_count` atomically |
| Comment | `POST /comments` — top-level or threaded reply via `parent_comment_id` |
| Delete comment | `DELETE /comments/{comment_id}` — author-only, cascades child replies |
| Feed | `GET /feed` — sort by `time` or `popularity`, configurable `limit` |
| User posts | `GET /users/{username}/posts` |
| Post comments | `GET /posts/{post_id}/comments` |
| AI chat | `POST /chat` — Vanna AI translates natural language → SQL → result |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/users` | Register a user |
| POST | `/posts` | Create a post |
| PUT | `/posts/{post_id}` | Edit a post (author only) |
| DELETE | `/posts/{post_id}` | Delete a post (author only) |
| POST | `/likes/toggle` | Toggle like on a post |
| POST | `/comments` | Add comment / reply |
| DELETE | `/comments/{comment_id}` | Delete comment (author only) |
| GET | `/feed` | Get feed (`?sort=time\|popularity&limit=20`) |
| GET | `/users/{username}/posts` | Get posts by user |
| GET | `/posts/{post_id}/comments` | Get comments on a post |
| POST | `/chat` | Vanna AI natural-language query |

All endpoints return JSON. Errors use standard HTTP status codes (`400`, `403`, `404`, `409`).

---

## Vanna AI Integration

Translates natural-language questions into SQL queries executed against `social_app.db`.

| Component | Value |
|---|---|
| LLM | DeepSeek (`deepseek-chat`) |
| SQL runner | SQLite (`social_app.db`) |
| Env variable | `DEEPSEEK_API_KEY` |

```bash
export DEEPSEEK_API_KEY=your_key_here
```

**Example:** `"Which user has the most likes in total?"` → SQL → `"alice (12 likes)"`

---

## Setup & Usage

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start server (database auto-initialised on first run)
python app.py
# or
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open **`http://127.0.0.1:8000/docs`** for Swagger UI, or open `demo_index.html` in a browser.

### Python installation (if needed)

| OS | Command |
|---|---|
| macOS | `brew install python` |
| Debian/Ubuntu | `sudo apt install python3 python3-pip` |
| Fedora | `sudo dnf install python3 python3-pip` |
| Windows | Download from [python.org](https://python.org) |

---

## Multi-device Access

1. Find your local IP — macOS: `ifconfig | grep "inet "` · Windows: `ipconfig` · Linux: `ip addr`
2. Open port 8000 on your firewall if needed
3. Run `python app.py`
4. On other devices, open `http://YOUR_IP:8000` in a browser, or open `demo_index.html` and enter the IP

---

## Running Tests

```bash
python test_db.py          # validate existing data (non-destructive)
python test_db.py --reset  # reset DB and seed demo data
```

| Test | What is verified |
|---|---|
| User creation | Unique username, fields |
| Post creation | Row count |
| Toggle like | `likes_count` increments / decrements correctly |
| Comments & replies | Threaded structure via `parent_comment_id` |
| Feed queries | Chronological and popularity ordering |
| User history | Filter posts by username |
| Cascade delete | Removing a user cleans up all related rows |
