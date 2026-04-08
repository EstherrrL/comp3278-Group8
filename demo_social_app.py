"""
demo_social_app.py
最基础的 HKUgram (Scenario 2) - 单文件版
"""

import os
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
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
from vanna.tools.agent_memory import SaveQuestionToolArgsTool, SearchSavedCorrectToolUsesTool
from vanna.integrations.local.agent_memory import DemoAgentMemory

DB_PATH = "./demo_social_app.sqlite"

# ===================== 数据库表 =====================
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  text_content TEXT,
  image_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  like_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS likes (
  user_id INTEGER NOT NULL,
  post_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, post_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_time ON posts(created_at DESC);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

init_db()

app = FastAPI(title="HKUgram - 最基础版")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="student", email="student@hku.hk", group_memberships=["user"])

tools = ToolRegistry()
tools.register_local_tool(RunSqlTool(sql_runner=SqliteRunner(DB_PATH)), access_groups=["admin", "user"])
tools.register_local_tool(VisualizeDataTool(), access_groups=["admin", "user"])

agent_memory = DemoAgentMemory(max_items=1000)
tools.register_local_tool(SaveQuestionToolArgsTool(), access_groups=["admin"])
tools.register_local_tool(SearchSavedCorrectToolUsesTool(), access_groups=["admin", "user"])

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

# ===================== 业务接口 =====================
class CreateUser(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)

class CreatePost(BaseModel):
    username: str
    text_content: Optional[str] = None
    image_url: Optional[str] = None

class LikePost(BaseModel):
    username: str
    post_id: int

@app.post("/users")
def create_user(req: CreateUser):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users (username) VALUES (?)", (req.username,))
    conn.commit()
    conn.close()
    return {"message": "用户创建成功"}

@app.post("/posts")
def create_post(req: CreatePost):
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "用户不存在")
    conn.execute("INSERT INTO posts (user_id, text_content, image_url) VALUES (?,?,?)",
                 (user["id"], req.text_content, req.image_url))
    conn.commit()
    conn.close()
    return {"message": "帖子发布成功"}

@app.post("/likes")
def like_post(req: LikePost):
    conn = get_conn()
    user = conn.execute("SELECT id FROM users WHERE username=?", (req.username,)).fetchone()
    if not user:
        raise HTTPException(404, "用户不存在")
    conn.execute("INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?,?)", (user["id"], req.post_id))
    conn.execute("UPDATE posts SET like_count = like_count + 1 WHERE id=?", (req.post_id,))
    conn.commit()
    conn.close()
    return {"message": "点赞成功"}

@app.get("/feed")
def get_feed(limit: int = 20):
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.id, u.username, p.text_content, p.image_url, p.created_at, p.like_count
        FROM posts p 
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

if __name__ == "__main__":
    import uvicorn
    print("🚀 HKUgram 最基础版已启动！")
    print("   → 访问 http://127.0.0.1:8000/docs 测试 API")
    print("   → 打开 demo_index.html 查看 Feed + Vanna 聊天框")
    uvicorn.run(app, host="0.0.0.0", port=8000)
