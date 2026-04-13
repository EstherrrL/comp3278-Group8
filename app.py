"""
app.py
HKUgram Group8 最终优化版 - 支持创建/切换用户 + 香港时间
"""

import os
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ===================== Vanna =====================
from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.openai import OpenAILlmService
from vanna.servers.fastapi.routes import register_chat_routes
from vanna.servers.base import ChatHandler
from vanna.core.user import UserResolver, User, RequestContext
from vanna.integrations.local.agent_memory import DemoAgentMemory

DB_PATH = "social_app.db"

app = FastAPI(title="HKUgram - Group8 最终优化版")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="student", email="student@hku.hk", group_memberships=["user"])

# ===================== Vanna 配置 =====================
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

# ===================== 手动 Vanna /chat =====================
@app.post("/chat")
async def vanna_chat(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "")
        if not question:
            return {"response": "请输入问题"}
        response = agent.ask(question)
        return {"response": response}
    except Exception as e:
        return {"response": f"Vanna 暂时无法回答: {str(e)}"}

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
    parent_comment_id: Optional[int] = None

# ===================== DB Helper =====================
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ===================== API =====================
@app.get("/users")
def get_users():
    conn = get_conn()
    rows = conn.execute("SELECT username FROM users").fetchall()
    conn.close()
    return [row["username"] for row in rows]

@app.post("/users")
def create_user(req: CreateUser):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO users (username) VALUES (?)", (req.username,))
        conn.commit()
        return {"message": "用户创建成功"}
    except sqlite3.IntegrityError:
        return {"message": "用户已存在"}
    finally:
        conn.close()

@app.post("/posts")
def create_post(req: CreatePost):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "用户不存在，请先创建用户")
    conn.execute("INSERT INTO posts (user_id, content, image_url) VALUES (?,?,?)",
                 (user["user_id"], req.content, req.image_url))
    conn.commit()
    conn.close()
    return {"message": "帖子发布成功"}

@app.post("/likes/toggle")
def toggle_like(req: ToggleLike):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user: raise HTTPException(404, "用户不存在")
    liked = conn.execute("SELECT 1 FROM likes WHERE user_id=? AND post_id=?", (user["user_id"], req.post_id)).fetchone()
    if liked:
        conn.execute("DELETE FROM likes WHERE user_id=? AND post_id=?", (user["user_id"], req.post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count - 1 WHERE post_id=?", (req.post_id,))
    else:
        conn.execute("INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?,?)", (user["user_id"], req.post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE post_id=?", (req.post_id,))
    conn.commit()
    conn.close()
    return {"message": "点赞操作成功"}

@app.post("/comments")
def create_comment(req: CreateComment):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user: raise HTTPException(404, "用户不存在")
    conn.execute("INSERT INTO comments (user_id, post_id, content, parent_comment_id) VALUES (?,?,?,?)",
                 (user["user_id"], req.post_id, req.content, req.parent_comment_id))
    conn.commit()
    conn.close()
    return {"message": "评论成功"}

@app.get("/feed")
def get_feed(sort: str = "time", limit: int = 20, search: Optional[str] = None):
    order_by = "p.timestamp DESC" if sort == "time" else "p.likes_count DESC"
    conn = get_conn()
    query = f"""
        SELECT p.post_id as id, u.username, p.content as text_content, 
               p.image_url, p.timestamp as created_at, p.likes_count as like_count
        FROM posts p JOIN users u ON p.user_id = u.user_id
    """
    params = []
    if search:
        query += " WHERE p.content LIKE ?"
        params.append(f"%{search}%")
    query += f" ORDER BY {order_by} LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/posts/{post_id}/comments")
def get_comments(post_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.timestamp, c.parent_comment_id
        FROM comments c JOIN users u ON c.user_id = u.user_id
        WHERE c.post_id = ? ORDER BY c.timestamp ASC
    """, (post_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

if __name__ == "__main__":
    import uvicorn
    print("🚀 HKUgram Group8 最终优化版已启动！（支持创建/切换用户 + 香港时间）")
    print("   → 访问 http://127.0.0.1:8000/docs")
    print("   → 打开 demo_index.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    