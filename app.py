"""
app.py
HKUgram Group8 最终完美版 - 完整功能版本
包含:用户系统、帖子、点赞、评论回复、搜索排序、Vanna AI、数据分析面板
基于FastAPI+SQLite的社交媒体后段API 
"""
#===================== 导入依赖库 =====================
import os
import json
import sqlite3
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import database as database_module

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

# ===================== 全局配置 =====================
# 数据库文件路径
DB_PATH = database_module.DB_PATH

app = FastAPI(title="HKUgram - Group8 最终完美版")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="student", email="student@hku.hk", group_memberships=["user"])

# ===================== Vanna setup =====================
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

# ===================== Vanna AI Implementation =====================
@app.post("/chat")
async def vanna_chat(request: Request):
    try:
        data = await request.json()
        question = data.get("question", "").strip()
        if not question:
            return {"response": "Please ask a question about users, posts, likes or comments."}

        # Get the database schema for context
        conn = get_conn()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

        schema_parts = []
        for table in tables:
            table_name = table['name']
            columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            col_list = [f"  {col['name']} ({col['type']})" for col in columns]
            schema_parts.append(f"Table: {table_name}\n" + "\n".join(col_list))
        conn.close()

        schema_text = "\n\n".join(schema_parts)

        # Use the agent to generate SQL
        context = RequestContext(user_id="student", user_email="student@hku.hk")
        response_generator = agent.send_message(
            request_context=context,
            message=f"""Given this database schema:
            {schema_text}

            For the question: "{question}"

            Generate a SQL query that:
            - Joins tables when needed to show meaningful information (e.g., usernames instead of user_ids, post content instead of just post_ids)
            - If asking about posts, include the post content and the author's username
            - If asking about likes, use the likes_count column from the posts table directly
            - Returns human-readable results

            Return ONLY the SQL query, no explanation."""
        )

        sql_query = ""
        async for chunk in response_generator:
            if hasattr(chunk, 'simple_component') and chunk.simple_component:
                comp = chunk.simple_component
                if hasattr(comp, 'text') and comp.text:
                    text = str(comp.text).strip()
                    if text.upper().startswith(('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH')):
                        sql_query = text
                        break

        if not sql_query:
            return {"response": "Could not generate SQL for your question. Please rephrase."}

        # Clean up SQL
        sql_query = sql_query.replace("```sql", "").replace("```", "").strip()

        # Execute the SQL query against social_app.db
        conn = get_conn()
        try:
            result = conn.execute(sql_query).fetchall()

            if not result:
                response = f"No results found for your question."
            else:
                # Format results nicely
                if len(result) == 1 and len(result[0].keys()) == 1:
                    # Single value result (e.g., COUNT)
                    value = list(result[0].values())[0]
                    response = f"{value}"
                else:
                    # Multiple rows/columns - format as text table
                    headers = list(result[0].keys())
                    response = ""

                    # Add header row
                    response += " | ".join(headers) + "\n"
                    response += "-" * 50 + "\n"

                    # Add data rows
                    for row in result[:20]:  # Limit to 20 rows
                        response += " | ".join(str(row[h]) for h in headers) + "\n"

                    if len(result) > 20:
                        response += f"\n... and {len(result) - 20} more rows"

        except Exception as e:
            response = f"Error executing query: {str(e)}\n\nSQL: {sql_query}"
        finally:
            conn.close()

        return {"response": response}

    except Exception as e:
        import traceback
        print("=" * 80)
        print("🚨 Chat Error:")
        traceback.print_exc()
        print("=" * 80)
        return {"response": f"Error: {str(e)}"}
    
# ===================== 时区工具：UTC → 北京时间 =====================
from datetime import datetime, timedelta

def utc_to_beijing(utc_str: str) -> str:
    """
    把数据库里的 UTC 时间字符串转成北京时间（+8小时)
    """
    if not utc_str:
        return utc_str
    try:
        utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        beijing_dt = utc_dt + timedelta(hours=8)
        return beijing_dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return utc_str

# ===================== Models =====================
#创建用户请求格式
class CreateUser(BaseModel):
    username: str

#发帖请求格式
class CreatePost(BaseModel):
    username: str
    content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[list[str]] = None


class UpdatePost(BaseModel):
    username: str
    content: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: Optional[list[str]] = None

#点赞/取消点赞请求格式
class ToggleLike(BaseModel):
    username: str
    post_id: int

#评论请求格式
class CreateComment(BaseModel):
    username: str
    post_id: int
    content: str
    parent_comment_id: Optional[int] = None

class DeleteComment(BaseModel):
    username: str


class DeletePost(BaseModel):
    username: str

# ===================== DB Helper =====================
def _sync_db_path() -> None:
    if database_module.DB_PATH != DB_PATH:
        database_module.set_db_path(DB_PATH)


def get_conn():
    _sync_db_path()
    return database_module.get_conn()


# ===================== 初始化数据库 =====================
def init_db():
    _sync_db_path()
    database_module.init_db()

# 初始化数据库
init_db()

# ===================== Helper Functions =====================
def get_user_id(username: str):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return user["user_id"] if user else None


def get_post_author_id(conn: sqlite3.Connection, post_id: int):
    post = conn.execute("SELECT user_id FROM posts WHERE post_id=?", (post_id,)).fetchone()
    return post["user_id"] if post else None


def normalize_image_urls(image_url: Optional[str], image_urls: Optional[list[str]]) -> list[str]:
    normalized_urls: list[str] = []

    for candidate in image_urls or []:
        if candidate is None:
            continue
        cleaned = candidate.strip()
        if cleaned:
            normalized_urls.append(cleaned)

    if image_url:
        cleaned_single_url = image_url.strip()
        if cleaned_single_url and cleaned_single_url not in normalized_urls:
            normalized_urls.insert(0, cleaned_single_url)

    return normalized_urls


def parse_image_urls(raw_image_urls: Optional[str], raw_image_url: Optional[str]) -> list[str]:
    image_urls: list[str] = []

    if raw_image_urls:
        try:
            decoded = json.loads(raw_image_urls)
            if isinstance(decoded, list):
                image_urls = [str(item).strip() for item in decoded if str(item).strip()]
        except json.JSONDecodeError:
            image_urls = []

    if not image_urls and raw_image_url:
        fallback_url = raw_image_url.strip()
        if fallback_url:
            image_urls = [fallback_url]

    return image_urls


def serialize_post_row(row: sqlite3.Row, include_username: bool = True) -> dict:
    post_dict = dict(row)
    image_urls = parse_image_urls(post_dict.get("image_urls"), post_dict.get("image_url"))
    post_dict["image_urls"] = image_urls
    post_dict["image_url"] = image_urls[0] if image_urls else None
    post_dict["created_at"] = utc_to_beijing(post_dict["created_at"])

    if not include_username:
        post_dict.pop("username", None)

    return post_dict

def get_liked_posts_by_user(username: str):
    """Get set of post IDs liked by a user"""
    conn = get_conn()
    user_id = get_user_id(username)
    if not user_id:
        conn.close()
        return set()
    rows = conn.execute("SELECT post_id FROM likes WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return {row["post_id"] for row in rows}

# ===================== API 端点 =====================
@app.get("/users")
def get_users():
    conn = get_conn()
    rows = conn.execute("SELECT username FROM users").fetchall()
    conn.close()
    return [row["username"] for row in rows]

@app.post("/users", status_code=201)
def create_user(req: CreateUser):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO users (username) VALUES (?)", (req.username,))
        conn.commit()
        return {"message": "User created successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already exists")
    finally:
        conn.close()

@app.post("/posts")
def create_post(req: CreatePost):
    image_urls = normalize_image_urls(req.image_url, req.image_urls)
    if not req.content and not image_urls:
        raise HTTPException(400, "Content and image cannot both be empty")

    conn = get_conn()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        conn.execute(
            "INSERT INTO posts (user_id, content, image_url, image_urls) VALUES (?,?,?,?)",
            (
                user["user_id"],
                req.content,
                image_urls[0] if image_urls else None,
                json.dumps(image_urls) if image_urls else None,
            ),
        )
        conn.commit()
        return {"message": "Post published successfully"}
    finally:
        conn.close()


@app.put("/posts/{post_id}")
def update_post(post_id: int, req: UpdatePost):
    image_urls = normalize_image_urls(req.image_url, req.image_urls)
    if not req.content and not image_urls:
        raise HTTPException(400, "Content and image cannot both be empty")

    conn = get_conn()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        post_author_id = get_post_author_id(conn, post_id)
        if post_author_id is None:
            raise HTTPException(404, "Post not found")

        if post_author_id != user["user_id"]:
            raise HTTPException(403, "You can only edit your own posts")

        conn.execute(
            "UPDATE posts SET content=?, image_url=?, image_urls=?, updated_at=CURRENT_TIMESTAMP WHERE post_id=?",
            (
                req.content,
                image_urls[0] if image_urls else None,
                json.dumps(image_urls) if image_urls else None,
                post_id,
            ),
        )
        conn.commit()
        return {"message": "Post updated successfully"}
    finally:
        conn.close()


@app.delete("/posts/{post_id}")
def delete_post(post_id: int, req: DeletePost):
    conn = get_conn()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        post_author_id = get_post_author_id(conn, post_id)
        if post_author_id is None:
            raise HTTPException(404, "Post not found")

        if post_author_id != user["user_id"]:
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
        conn.execute("BEGIN IMMEDIATE")
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        post = conn.execute("SELECT 1 FROM posts WHERE post_id=?", (req.post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "Post not found")

        deleted = conn.execute(
            "DELETE FROM likes WHERE user_id=? AND post_id=?",
            (user["user_id"], req.post_id),
        ).rowcount
        if deleted:
            conn.execute(
                "UPDATE posts SET likes_count = MAX(likes_count - 1, 0) WHERE post_id=?",
                (req.post_id,),
            )
        else:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO likes (user_id, post_id) VALUES (?,?)",
                (user["user_id"], req.post_id),
            ).rowcount
            if inserted:
                conn.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE post_id=?", (req.post_id,))

        conn.commit()
        return {"message": "Like toggled successfully"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@app.post("/comments")
def create_comment(req: CreateComment):
    conn = get_conn()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        post = conn.execute("SELECT 1 FROM posts WHERE post_id=?", (req.post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "Post not found")

        if req.parent_comment_id:
            parent = conn.execute(
                "SELECT 1 FROM comments WHERE comment_id=? AND post_id=?",
                (req.parent_comment_id, req.post_id),
            ).fetchone()
            if not parent:
                raise HTTPException(404, "Parent comment not found")

        conn.execute(
            """INSERT INTO comments (user_id, post_id, content, parent_comment_id)
                   VALUES (?,?,?,?)""",
            (user["user_id"], req.post_id, req.content, req.parent_comment_id),
        )
        conn.commit()
        return {"message": "Comment added successfully"}
    finally:
        conn.close()

@app.delete("/comments/{comment_id}")
def delete_comment(comment_id: int, req: DeleteComment):
    conn = get_conn()
    try:
        user = conn.execute("SELECT user_id FROM users WHERE username=?", (req.username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        comment = conn.execute("SELECT user_id FROM comments WHERE comment_id=?", (comment_id,)).fetchone()
        if not comment:
            raise HTTPException(404, "Comment not found")

        if comment["user_id"] != user["user_id"]:
            raise HTTPException(403, "You can only delete your own comments")

        conn.execute("DELETE FROM comments WHERE comment_id=?", (comment_id,))
        conn.commit()
        return {"message": "Comment deleted successfully"}
    finally:
        conn.close()

@app.get("/feed")
def get_feed(sort: str = "time", limit: int = 50, search: Optional[str] = None, viewer: Optional[str] = None):
    order_by = "p.timestamp DESC" if sort == "time" else "p.likes_count DESC"
    conn = get_conn()
    query = f"""
        SELECT p.post_id as id, u.username, p.content as text_content, 
               p.image_url, p.image_urls, p.timestamp as created_at, p.likes_count as like_count
        FROM posts p JOIN users u ON p.user_id = u.user_id
    """
    params = []
    if search:
        query += " WHERE p.content LIKE ?"
        params.append(f"%{search}%")
    query += f" ORDER BY {order_by} LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    
    # Get liked posts for viewer
    liked_posts = get_liked_posts_by_user(viewer) if viewer else set()
    
    result = []
    for row in rows:
        post_dict = serialize_post_row(row)
        post_dict["liked_by_viewer"] = post_dict["id"] in liked_posts
        result.append(post_dict)
    
    conn.close()
    return result

@app.get("/users/{username}/posts")
def get_user_posts(username: str, viewer: Optional[str] = None):
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    
    rows = conn.execute("""
         SELECT p.post_id as id, p.content as text_content,
             p.image_url, p.image_urls, p.timestamp as created_at, p.likes_count as like_count
        FROM posts p
        WHERE p.user_id = ?
        ORDER BY p.timestamp DESC
    """, (user["user_id"],)).fetchall()
    
    # Get liked posts for viewer
    liked_posts = get_liked_posts_by_user(viewer) if viewer else set()
    
    result = []
    for row in rows:
        post_dict = serialize_post_row(row, include_username=False)
        post_dict["liked_by_viewer"] = post_dict["id"] in liked_posts
        result.append(post_dict)
    
    conn.close()
    return result

@app.get("/posts/{post_id}/comments")
def get_comments(post_id: int):
    conn = get_conn()
    # Get all comments for this post
    rows = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.timestamp, c.parent_comment_id
        FROM comments c JOIN users u ON c.user_id = u.user_id
        WHERE c.post_id = ? ORDER BY c.timestamp ASC
    """, (post_id,)).fetchall()
    conn.close()
    
    # Build comment tree structure
    comments = [dict(row) for row in rows]
    for comment in comments:
        comment['timestamp'] = utc_to_beijing(comment['timestamp'])
    
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
        raise HTTPException(404, "Comment not found")
    return dict(row)

# ===================== 分析功能 (Analytics) =====================

@app.get("/analytics/top-posts")
def get_top_posts(limit: int = 10):
    """获取最受欢迎的帖子（按点赞数）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.post_id as id, u.username, p.content as text_content,
               p.image_url, p.image_urls, p.timestamp as created_at, p.likes_count as like_count
        FROM posts p JOIN users u ON p.user_id = u.user_id
        ORDER BY p.likes_count DESC, p.timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    # 转成北京/香港时间
    result = []
    for row in rows:
        row_dict = serialize_post_row(row)
        result.append(row_dict)
    return result

@app.get("/analytics/most-active-users")
def get_most_active_users(limit: int = 10):
    """获取最活跃的用户（按发帖数）"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.username, COUNT(p.post_id) as post_count,
               SUM(p.likes_count) as total_likes
        FROM users u LEFT JOIN posts p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.username
        ORDER BY post_count DESC, total_likes DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/analytics/user-stats/{username}")
def get_user_stats(username: str):
    """获取用户的详细统计信息"""
    conn = get_conn()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    
    user_id = user["user_id"]
    
    # 获取用户发帖数
    post_stats = conn.execute("""
        SELECT COUNT(p.post_id) as total_posts,
               SUM(p.likes_count) as total_likes,
               AVG(p.likes_count) as avg_likes
        FROM posts p
        WHERE p.user_id = ?
    """, (user_id,)).fetchone()
    
    # 获取用户评论数
    comment_stats = conn.execute("""
        SELECT COUNT(c.comment_id) as total_comments
        FROM comments c
        WHERE c.user_id = ?
    """, (user_id,)).fetchone()
    
    # 获取用户给出的点赞数
    likes_given = conn.execute("""
        SELECT COUNT(*) as likes_given
        FROM likes l
        WHERE l.user_id = ?
    """, (user_id,)).fetchone()
    
    conn.close()
    
    return {
        "username": username,
        "total_posts": post_stats["total_posts"] or 0,
        "total_likes": post_stats["total_likes"] or 0,
        "avg_likes_per_post": round(post_stats["avg_likes"] or 0, 2),
        "total_comments": comment_stats["total_comments"] or 0,
        "likes_given": likes_given["likes_given"] or 0
    }

@app.get("/analytics/top-liked-users")
def get_top_liked_users(limit: int = 10):
    """获取获赞最多的用户"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.username, SUM(p.likes_count) as total_likes,
               COUNT(p.post_id) as post_count
        FROM users u LEFT JOIN posts p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.username
        HAVING total_likes > 0
        ORDER BY total_likes DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

#平台数据总览
@app.get("/analytics/dashboard")
def get_dashboard_stats():
    """获取整个平台的统计信息"""
    conn = get_conn()
    
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
    total_posts = conn.execute("SELECT COUNT(*) as count FROM posts").fetchone()
    total_comments = conn.execute("SELECT COUNT(*) as count FROM comments").fetchone()
    total_likes = conn.execute("SELECT COUNT(*) as count FROM likes").fetchone()
    
    # 最受欢迎的帖子
    top_post = conn.execute("""
        SELECT p.post_id as id, u.username, p.content as text_content,
               p.likes_count as like_count
        FROM posts p JOIN users u ON p.user_id = u.user_id
        ORDER BY p.likes_count DESC
        LIMIT 1
    """).fetchone()
    
    # 最活跃的用户
    most_active = conn.execute("""
        SELECT u.username, COUNT(p.post_id) as post_count
        FROM users u LEFT JOIN posts p ON u.user_id = p.user_id
        GROUP BY u.user_id, u.username
        ORDER BY post_count DESC
        LIMIT 1
    """).fetchone()
    
    conn.close()
    
    return {
        "total_users": total_users["count"] or 0,
        "total_posts": total_posts["count"] or 0,
        "total_comments": total_comments["count"] or 0,
        "total_likes": total_likes["count"] or 0,
        "most_popular_post": dict(top_post) if top_post else None,
        "most_active_user": dict(most_active) if most_active else None
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 HKUgram Group8 Final Version Started!")
    print("   → Visit http://127.0.0.1:8000/docs")
    print("   → Open demo_index.html")
    print("   → Analytics available at /analytics/*")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
