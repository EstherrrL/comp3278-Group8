"""
app.py
HKUgram Group8 升级版 - 支持 Toggle Like + 评论回复 + 排序 + 用户历史
"""

import os
import sqlite3
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ===================== Vanna 配置 =====================
from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.openai import OpenAILlmService
from vanna.servers.fastapi.routes import register_chat_routes
from vanna.servers.base import ChatHandler
from vanna.core.user import UserResolver, User, RequestContext
from vanna.integrations.local.agent_memory import DemoAgentMemory

# ===================== 数据库（统一从 database 模块引入）=====================
from database import DB_PATH, get_conn, init_db  # noqa: F401  init_db 在 import 时自动运行

app = FastAPI(title="HKUgram - Group8 升级版")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="student", email="student@hku.hk", group_memberships=["user"])

# ===================== Vanna =====================
tools = ToolRegistry()
tools.register_local_tool(RunSqlTool(sql_runner=SqliteRunner(DB_PATH)), access_groups=["admin", "user"])
tools.register_local_tool(VisualizeDataTool(), access_groups=["admin", "user"])

agent_memory = DemoAgentMemory(max_items=1000)
llm = OpenAILlmService(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1"
)

agent = Agent(
    llm_service=llm,
    tool_registry=tools,
    user_resolver=SimpleUserResolver(),
    config=AgentConfig(max_tool_iterations=50),
    agent_memory=agent_memory
)

chat_handler = ChatHandler(agent)
register_chat_routes(app, chat_handler)

# ===================== Models =====================
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
    parent_comment_id: Optional[int] = None   # 用于回复

class DeleteComment(BaseModel):
    username: str

# ===================== API =====================
@app.post("/users")
def create_user(req: CreateUser):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (req.username,))
    conn.commit()
    conn.close()
    return {"message": "User created successfully"}

@app.get("/users")
def list_users():
    conn = get_conn()
    rows = conn.execute(
        "SELECT username FROM users ORDER BY timestamp DESC, username ASC"
    ).fetchall()
    conn.close()
    return [row["username"] for row in rows]

@app.post("/posts")
def create_post(req: CreatePost):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    conn.execute("INSERT INTO posts (user_id, content, image_url) VALUES (?,?,?)",
                 (user["user_id"], req.content, req.image_url))
    conn.commit()
    conn.close()
    return {"message": "Post published successfully"}

@app.post("/likes/toggle")
def toggle_like(req: ToggleLike):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    
    # 检查是否已点赞
    liked = conn.execute("SELECT 1 FROM likes WHERE user_id=? AND post_id=?", 
                        (user["user_id"], req.post_id)).fetchone()
    
    if liked:
        # 取消点赞
        conn.execute("DELETE FROM likes WHERE user_id=? AND post_id=?", 
                    (user["user_id"], req.post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count - 1 WHERE post_id=?", 
                    (req.post_id,))
        action = "Like removed"
    else:
        # 点赞
        conn.execute("INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?,?)", 
                    (user["user_id"], req.post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE post_id=?", 
                    (req.post_id,))
        action = "Post liked"
    
    conn.commit()
    conn.close()
    return {"message": action}

@app.post("/comments")
def create_comment(req: CreateComment):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    conn.execute("""
        INSERT INTO comments (user_id, post_id, content, parent_comment_id) 
        VALUES (?,?,?,?)
    """, (user["user_id"], req.post_id, req.content, req.parent_comment_id))
    conn.commit()
    conn.close()
    return {"message": "Comment added successfully"}

@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, req: DeleteComment):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(404, "User not found")

    comment = conn.execute(
        "SELECT user_id FROM comments WHERE comment_id=?",
        (comment_id,)
    ).fetchone()
    if not comment:
        conn.close()
        raise HTTPException(404, "Comment not found")

    if comment["user_id"] != user["user_id"]:
        conn.close()
        raise HTTPException(403, "You can only delete your own comments")

    conn.execute("DELETE FROM comments WHERE comment_id=?", (comment_id,))
    conn.commit()
    conn.close()
    return {"message": "Comment deleted"}

@app.get("/feed")
def get_feed(sort: str = "time", limit: int = 20, viewer: Optional[str] = None):
    order_by = "p.timestamp DESC" if sort == "time" else "p.likes_count DESC"
    conn = get_conn()
    if viewer:
        rows = conn.execute(f"""
            SELECT p.post_id as id, u.username, p.content as text_content,
                   p.image_url, p.timestamp as created_at, p.likes_count as like_count,
                   EXISTS(
                       SELECT 1
                       FROM likes l
                       JOIN users vu ON vu.user_id = l.user_id
                       WHERE l.post_id = p.post_id AND vu.username = ?
                   ) as liked_by_viewer
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY {order_by} LIMIT ?
        """, (viewer, limit)).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT p.post_id as id, u.username, p.content as text_content,
                   p.image_url, p.timestamp as created_at, p.likes_count as like_count,
                   0 as liked_by_viewer
            FROM posts p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY {order_by} LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/users/{username}/posts")
def get_user_posts(username: str):
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.post_id as id, p.content as text_content, p.image_url, 
               p.timestamp as created_at, p.likes_count as like_count
        FROM posts p 
        JOIN users u ON p.user_id = u.user_id
        WHERE u.username = ?
        ORDER BY p.timestamp DESC
    """, (username,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/posts/{post_id}/comments")
def get_comments(post_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.timestamp, 
               c.parent_comment_id
        FROM comments c
        JOIN users u ON c.user_id = u.user_id
        WHERE c.post_id = ?
        ORDER BY c.timestamp ASC
    """, (post_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ===================== 启动 =====================
if __name__ == "__main__":
    import uvicorn
    print("🚀 HKUgram Group8 升级版已启动！（Toggle Like + 评论回复 + 排序）")
    print("   → http://127.0.0.1:8000/docs 测试 API")
    print("   → 打开 demo_index.html 查看完整界面")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    