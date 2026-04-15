"""FastAPI application for HKUgram."""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import DB_PATH, get_conn, init_db  # noqa: F401

try:
    from vanna import Agent, AgentConfig
    from vanna.core.registry import ToolRegistry
    from vanna.core.user import RequestContext, User, UserResolver
    from vanna.integrations.local.agent_memory import DemoAgentMemory
    from vanna.integrations.openai import OpenAILlmService
    from vanna.integrations.sqlite import SqliteRunner
    from vanna.servers.base import ChatHandler
    from vanna.servers.fastapi.routes import register_chat_routes
    from vanna.tools import RunSqlTool, VisualizeDataTool
except ImportError:
    Agent = None
    AgentConfig = None
    ToolRegistry = None
    RequestContext = Any
    User = Any
    UserResolver = object
    DemoAgentMemory = None
    OpenAILlmService = None
    SqliteRunner = None
    ChatHandler = None
    register_chat_routes = None
    RunSqlTool = None
    VisualizeDataTool = None


app = FastAPI(title="HKUgram - Group8")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class CreateUser(BaseModel):
    username: str


class CreatePost(BaseModel):
    username: str
    content: Optional[str] = None
    image_url: Optional[str] = None


class ToggleLike(BaseModel):
    username: str
    post_id: int


class CreateComment(BaseModel):
    username: str
    post_id: int
    content: str
    parent_comment_id: Optional[int] = None


class DeleteComment(BaseModel):
    username: str


class DeletePost(BaseModel):
    username: str


class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context):
        return User(id="student", email="student@hku.hk", group_memberships=["user"])


def fetch_user(conn, username: str):
    return conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()


def fetch_post(conn, post_id: int):
    return conn.execute("SELECT post_id FROM posts WHERE post_id=?", (post_id,)).fetchone()


def build_vanna_agent():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or not Agent:
        return None

    try:
        tools = ToolRegistry()
        tools.register_local_tool(RunSqlTool(sql_runner=SqliteRunner(DB_PATH)), access_groups=["admin", "user"])
        tools.register_local_tool(VisualizeDataTool(), access_groups=["admin", "user"])

        llm = OpenAILlmService(
            api_key=api_key,
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )

        return Agent(
            llm_service=llm,
            tool_registry=tools,
            user_resolver=SimpleUserResolver(),
            config=AgentConfig(max_tool_iterations=50),
            agent_memory=DemoAgentMemory(max_items=1000),
        )
    except Exception:
        return None


agent = build_vanna_agent()
if agent and register_chat_routes and ChatHandler:
    register_chat_routes(app, ChatHandler(agent))


@app.post("/chat")
async def vanna_chat(request: Request):
    if not agent:
        return {"response": "AI chat is unavailable. Set DEEPSEEK_API_KEY to enable it."}

    try:
        data = await request.json()
        question = (data.get("question") or "").strip()
        if not question:
            return {"response": "Please enter a question."}
        return {"response": agent.ask(question)}
    except Exception as exc:
        return {"response": f"Vanna is temporarily unavailable: {exc}"}


@app.post("/users")
def create_user(req: CreateUser):
    username = req.username.strip()
    if not username:
        raise HTTPException(400, "Username cannot be empty")

    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (username,))
        conn.commit()
        return {"message": "User created successfully"}
    finally:
        conn.close()


@app.get("/users")
def list_users():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT username FROM users ORDER BY timestamp DESC, username ASC"
        ).fetchall()
        return [row["username"] for row in rows]
    finally:
        conn.close()


@app.post("/posts")
def create_post(req: CreatePost):
    content = req.content.strip() if req.content else None
    image_url = req.image_url.strip() if req.image_url else None
    if not content and not image_url:
        raise HTTPException(400, "Post content and image cannot both be empty")

    conn = get_conn()
    try:
        user = fetch_user(conn, req.username)
        if not user:
            raise HTTPException(404, "User not found")

        conn.execute(
            "INSERT INTO posts (user_id, content, image_url) VALUES (?,?,?)",
            (user["user_id"], content, image_url),
        )
        conn.commit()
        return {"message": "Post published successfully"}
    finally:
        conn.close()


@app.delete("/posts/{post_id}")
def delete_post(post_id: int, req: DeletePost):
    conn = get_conn()
    try:
        user = fetch_user(conn, req.username)
        if not user:
            raise HTTPException(404, "User not found")

        post = conn.execute(
            "SELECT user_id FROM posts WHERE post_id=?",
            (post_id,),
        ).fetchone()
        if not post:
            raise HTTPException(404, "Post not found")
        if post["user_id"] != user["user_id"]:
            raise HTTPException(403, "You can only delete your own posts")

        conn.execute("DELETE FROM posts WHERE post_id=?", (post_id,))
        conn.commit()
        return {"message": "Post deleted successfully"}
    finally:
        conn.close()


@app.post("/likes/toggle")
def toggle_like(req: ToggleLike):
    conn = get_conn()
    try:
        user = fetch_user(conn, req.username)
        if not user:
            raise HTTPException(404, "User not found")
        if not fetch_post(conn, req.post_id):
            raise HTTPException(404, "Post not found")

        liked = conn.execute(
            "SELECT 1 FROM likes WHERE user_id=? AND post_id=?",
            (user["user_id"], req.post_id),
        ).fetchone()

        if liked:
            conn.execute("DELETE FROM likes WHERE user_id=? AND post_id=?", (user["user_id"], req.post_id))
            conn.execute(
                "UPDATE posts SET likes_count = MAX(likes_count - 1, 0) WHERE post_id=?",
                (req.post_id,),
            )
            action = "Like removed"
        else:
            conn.execute("INSERT INTO likes (user_id, post_id) VALUES (?,?)", (user["user_id"], req.post_id))
            conn.execute(
                "UPDATE posts SET likes_count = likes_count + 1 WHERE post_id=?",
                (req.post_id,),
            )
            action = "Post liked"

        conn.commit()
        return {"message": action}
    finally:
        conn.close()


@app.post("/comments")
def create_comment(req: CreateComment):
    content = req.content.strip()
    if not content:
        raise HTTPException(400, "Comment content cannot be empty")

    conn = get_conn()
    try:
        user = fetch_user(conn, req.username)
        if not user:
            raise HTTPException(404, "User not found")
        if not fetch_post(conn, req.post_id):
            raise HTTPException(404, "Post not found")

        if req.parent_comment_id is not None:
            parent = conn.execute(
                "SELECT comment_id, post_id FROM comments WHERE comment_id=?",
                (req.parent_comment_id,),
            ).fetchone()
            if not parent:
                raise HTTPException(404, "Parent comment not found")
            if parent["post_id"] != req.post_id:
                raise HTTPException(400, "Reply must belong to the same post")

        conn.execute(
            "INSERT INTO comments (user_id, post_id, content, parent_comment_id) VALUES (?,?,?,?)",
            (user["user_id"], req.post_id, content, req.parent_comment_id),
        )
        conn.commit()
        return {"message": "Comment added successfully"}
    finally:
        conn.close()


@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, req: DeleteComment):
    conn = get_conn()
    try:
        user = fetch_user(conn, req.username)
        if not user:
            raise HTTPException(404, "User not found")

        comment = conn.execute(
            "SELECT user_id FROM comments WHERE comment_id=?",
            (comment_id,),
        ).fetchone()
        if not comment:
            raise HTTPException(404, "Comment not found")
        if comment["user_id"] != user["user_id"]:
            raise HTTPException(403, "You can only delete your own comments")

        conn.execute("DELETE FROM comments WHERE comment_id=?", (comment_id,))
        conn.commit()
        return {"message": "Comment deleted"}
    finally:
        conn.close()


@app.get("/feed")
def get_feed(sort: str = "time", limit: int = 20, viewer: Optional[str] = None):
    order_by = "p.timestamp DESC" if sort == "time" else "p.likes_count DESC, p.timestamp DESC"
    conn = get_conn()
    try:
        if viewer:
            rows = conn.execute(
                f"""
                SELECT p.post_id AS id, u.username, p.content AS text_content,
                       p.image_url, p.timestamp AS created_at, p.likes_count AS like_count,
                       EXISTS(
                           SELECT 1
                           FROM likes l
                           JOIN users vu ON vu.user_id = l.user_id
                           WHERE l.post_id = p.post_id AND vu.username = ?
                       ) AS liked_by_viewer
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                ORDER BY {order_by} LIMIT ?
                """,
                (viewer, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT p.post_id AS id, u.username, p.content AS text_content,
                       p.image_url, p.timestamp AS created_at, p.likes_count AS like_count,
                       0 AS liked_by_viewer
                FROM posts p
                JOIN users u ON p.user_id = u.user_id
                ORDER BY {order_by} LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/users/{username}/posts")
def get_user_posts(username: str):
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT p.post_id AS id, p.content AS text_content, p.image_url,
                   p.timestamp AS created_at, p.likes_count AS like_count
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
            WHERE u.username = ?
            ORDER BY p.timestamp DESC
            """,
            (username,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/posts/{post_id}/comments")
def get_comments(post_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.comment_id, u.username, c.content, c.timestamp, c.parent_comment_id
            FROM comments c
            JOIN users u ON c.user_id = u.user_id
            WHERE c.post_id = ?
            ORDER BY c.timestamp ASC, c.comment_id ASC
            """,
            (post_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
