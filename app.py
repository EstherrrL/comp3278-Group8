"""
app.py
HKUgram Group8 最终完美版 - 修复所有 404/405 + 用户切换 + 香港时间 + 评论回复功能
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

app = FastAPI(title="HKUgram - Group8 最终完美版")
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

# ===================== 初始化数据库 =====================
def init_db():
    conn = get_conn()
    # 创建用户表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL
        )
    """)
    # 创建帖子表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            post_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT,
            image_url TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            likes_count INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    # 创建点赞表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            like_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (post_id) REFERENCES posts(post_id),
            UNIQUE(user_id, post_id)
        )
    """)
    # 创建评论表（支持嵌套回复）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            parent_comment_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (post_id) REFERENCES posts(post_id),
            FOREIGN KEY (parent_comment_id) REFERENCES comments(comment_id)
        )
    """)
    conn.commit()
    conn.close()

# 初始化数据库
init_db()

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
        return {"message": "用户名已存在"}
    finally:
        conn.close()

@app.post("/posts")
def create_post(req: CreatePost):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "用户不存在")
    conn.execute("INSERT INTO posts (user_id, content, image_url) VALUES (?,?,?)",
                 (user["user_id"], req.content, req.image_url))
    conn.commit()
    conn.close()
    return {"message": "帖子发布成功"}

@app.post("/likes/toggle")
def toggle_like(req: ToggleLike):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user: 
        raise HTTPException(404, "用户不存在")
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
    if not user: 
        raise HTTPException(404, "用户不存在")
    
    # 如果 parent_comment_id 存在，验证父评论是否存在
    if req.parent_comment_id:
        parent = conn.execute("SELECT 1 FROM comments WHERE comment_id=?", (req.parent_comment_id,)).fetchone()
        if not parent:
            raise HTTPException(404, "父评论不存在")
    
    conn.execute("""INSERT INTO comments (user_id, post_id, content, parent_comment_id) 
                   VALUES (?,?,?,?)""",
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
    # 获取所有评论
    rows = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.timestamp, c.parent_comment_id
        FROM comments c JOIN users u ON c.user_id = u.user_id
        WHERE c.post_id = ? ORDER BY c.timestamp ASC
    """, (post_id,)).fetchall()
    conn.close()
    
    # 构建评论树结构
    comments = [dict(row) for row in rows]
    comment_dict = {c['comment_id']: {**c, 'replies': []} for c in comments}
    root_comments = []
    
    for comment in comments:
        if comment['parent_comment_id'] is None:
            root_comments.append(comment_dict[comment['comment_id']])
        else:
            if comment['parent_comment_id'] in comment_dict:
                comment_dict[comment['parent_comment_id']]['replies'].append(comment_dict[comment['comment_id']])
    
    return root_comments

@app.get("/comments/{comment_id}")
def get_comment(comment_id: int):
    conn = get_conn()
    row = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.post_id
        FROM comments c JOIN users u ON c.user_id = u.user_id
        WHERE c.comment_id = ?
    """, (comment_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "评论不存在")
    return dict(row)

if __name__ == "__main__":
    import uvicorn
    print("🚀 HKUgram Group8 最终完美版已启动！")
    print("   → 访问 http://127.0.0.1:8000/docs")
    print("   → 打开 demo_index.html")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    