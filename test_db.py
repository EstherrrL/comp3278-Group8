"""
test_db.py
HKUgram Group8 — 数据库测试 & 演示数据填充脚本

运行方式：
    python test_db.py          # 重置并填充演示数据（用于 demo）
    python test_db.py --check  # 仅验证现有数据，不修改数据库

测试内容：
  1. 建表 & 迁移（通过 database.init_db）
  2. 用户 CRUD
  3. 发帖 CRUD
  4. Toggle 点赞（点赞 → 取消点赞 → 再点赞）
  5. 评论 & 楼中楼回复
  6. Feed 排序查询（按时间 / 按人气）
  7. 用户历史帖子查询
  8. 外键级联删除
"""

import sys
import sqlite3
from database import DB_PATH, init_db, get_conn

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────
def section(title: str):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)

def ok(msg: str):
    print(f"  ✅  {msg}")

def fail(msg: str):
    print(f"  ❌  {msg}")
    sys.exit(1)

def assert_eq(label, actual, expected):
    if actual == expected:
        ok(f"{label}: {actual!r}")
    else:
        fail(f"{label} 期望 {expected!r}，实际 {actual!r}")

# ──────────────────────────────────────────────
# 重置数据库（仅在演示填充模式下）
# ──────────────────────────────────────────────
def reset_db():
    """删除并重新初始化数据库，用于演示环境。"""
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"  🗑  已删除旧数据库: {DB_PATH}")
    init_db()
    print(f"  🆕  数据库已初始化: {DB_PATH}")

# ──────────────────────────────────────────────
# 测试 1：用户创建
# ──────────────────────────────────────────────
def test_users(conn):
    section("TEST 1 — 用户创建")
    users = [
        ("alice",  "alice@hku.hk",  "喜欢摄影 📷",       None),
        ("bob",    "bob@hku.hk",    "CS 大三 🖥️",         None),
        ("carol",  "carol@hku.hk",  "HKU 交换生 🌏",      None),
        ("david",  "david@hku.hk",  "爱好跑步 🏃",        None),
        ("eve",    "eve@hku.hk",    "音乐人 🎵",           None),
    ]
    for username, email, bio, profile_pic in users:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, bio, profile_pic) VALUES (?,?,?,?)",
            (username, email, bio, profile_pic)
        )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert_eq("用户总数", count, 5)

    alice = conn.execute("SELECT * FROM users WHERE username='alice'").fetchone()
    assert_eq("alice.email", alice["email"], "alice@hku.hk")
    assert_eq("alice.bio",   alice["bio"],   "喜欢摄影 📷")

# ──────────────────────────────────────────────
# 测试 2：帖子发布
# ──────────────────────────────────────────────
def test_posts(conn):
    section("TEST 2 — 帖子发布")
    posts = [
        (1, "大家好，我是 Alice！第一天来 HKUgram 🥳",    None),
        (2, "今天 CS 作业好难…有没有人一起讨论？",          None),
        (3, "香港太好玩了！刚去了维港 🌆",                  "https://picsum.photos/seed/harbour/800/500"),
        (1, "新发现一家超好吃的茶餐厅！地点：旺角 🍜",      "https://picsum.photos/seed/food/800/500"),
        (4, "今天晨跑 10km，状态极佳 💪",                   None),
        (5, "刚录了一首新歌，求大家听听 🎶",                 None),
        (2, "期中考结束！解放了 🎉",                         "https://picsum.photos/seed/party/800/500"),
        (3, "HKU 图书馆的夜景真的很美 📚",                  "https://picsum.photos/seed/library/800/500"),
    ]
    for user_id, content, image_url in posts:
        conn.execute(
            "INSERT INTO posts (user_id, content, image_url) VALUES (?,?,?)",
            (user_id, content, image_url)
        )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    assert_eq("帖子总数", count, 8)

# ──────────────────────────────────────────────
# 测试 3：Toggle 点赞
# ──────────────────────────────────────────────
def toggle_like(conn, user_id: int, post_id: int) -> str:
    liked = conn.execute(
        "SELECT 1 FROM likes WHERE user_id=? AND post_id=?", (user_id, post_id)
    ).fetchone()
    if liked:
        conn.execute("DELETE FROM likes WHERE user_id=? AND post_id=?", (user_id, post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count - 1 WHERE post_id=?", (post_id,))
        conn.commit()
        return "unlike"
    else:
        conn.execute("INSERT INTO likes (user_id, post_id) VALUES (?,?)", (user_id, post_id))
        conn.execute("UPDATE posts SET likes_count = likes_count + 1 WHERE post_id=?", (post_id,))
        conn.commit()
        return "like"

def test_likes(conn):
    section("TEST 3 — Toggle 点赞")

    # 多用户对多帖子点赞
    like_pairs = [
        (1, 3), (1, 4), (1, 7),
        (2, 1), (2, 3), (2, 8),
        (3, 1), (3, 2), (3, 4), (3, 7),
        (4, 1), (4, 5),
        (5, 6), (5, 7),
    ]
    for uid, pid in like_pairs:
        action = toggle_like(conn, uid, pid)
        ok(f"user {uid} → post {pid}: {action}")

    # 验证 post 1 的点赞数（user 2、3、4 点赞 → 共 3）
    lc = conn.execute("SELECT likes_count FROM posts WHERE post_id=1").fetchone()[0]
    assert_eq("post 1 likes_count", lc, 3)

    # Toggle 取消：user 2 对 post 1 取消点赞
    action = toggle_like(conn, 2, 1)
    assert_eq("user2 取消 post1", action, "unlike")
    lc = conn.execute("SELECT likes_count FROM posts WHERE post_id=1").fetchone()[0]
    assert_eq("取消后 post 1 likes_count", lc, 2)

    # 再点赞
    action = toggle_like(conn, 2, 1)
    assert_eq("user2 再点赞 post1", action, "like")
    lc = conn.execute("SELECT likes_count FROM posts WHERE post_id=1").fetchone()[0]
    assert_eq("再点赞后 post 1 likes_count", lc, 3)

# ──────────────────────────────────────────────
# 测试 4：评论 & 楼中楼
# ──────────────────────────────────────────────
def test_comments(conn):
    section("TEST 4 — 评论 & 楼中楼回复")

    # 顶级评论
    top_comments = [
        (2, 1, None, "欢迎 Alice！这里很好玩 🎉"),
        (3, 1, None, "Alice 终于来了！"),
        (4, 3, None, "维港真的很漂亮，上周我也去了！"),
        (5, 7, None, "恭喜 Bob 期中考完！"),
        (1, 5, None, "好厉害，10km！怎么训练的？"),
    ]
    comment_ids = []
    for uid, pid, parent, content in top_comments:
        cursor = conn.execute(
            "INSERT INTO comments (user_id, post_id, parent_comment_id, content) VALUES (?,?,?,?)",
            (uid, pid, parent, content)
        )
        comment_ids.append(cursor.lastrowid)
    conn.commit()

    # 楼中楼回复（回复第一条评论）
    replies = [
        (1, 1, comment_ids[0], "谢谢！😊 大家多多关照~"),
        (2, 1, comment_ids[1], "哈哈 等你很久啦 Alice！"),
        (3, 5, comment_ids[4], "每天早上 6 点跑！坚持就是胜利 💪"),
    ]
    for uid, pid, parent, content in replies:
        conn.execute(
            "INSERT INTO comments (user_id, post_id, parent_comment_id, content) VALUES (?,?,?,?)",
            (uid, pid, parent, content)
        )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    assert_eq("评论总数（含回复）", total, 8)

    # 验证 post 1 的楼中楼
    thread = conn.execute("""
        SELECT c.comment_id, u.username, c.content, c.parent_comment_id
        FROM comments c JOIN users u ON c.user_id = u.user_id
        WHERE c.post_id = 1
        ORDER BY c.timestamp ASC
    """).fetchall()
    ok(f"post 1 评论树（共 {len(thread)} 条）:")
    for row in thread:
        indent = "  └─ " if row["parent_comment_id"] else "  "
        print(f"      {indent}[{row['comment_id']}] @{row['username']}: {row['content']}")

# ──────────────────────────────────────────────
# 测试 5：Feed 查询
# ──────────────────────────────────────────────
def test_feed(conn):
    section("TEST 5 — Feed 查询")

    # 按时间
    rows_time = conn.execute("""
        SELECT p.post_id, u.username, p.content, p.likes_count, p.timestamp
        FROM posts p JOIN users u ON p.user_id = u.user_id
        ORDER BY p.timestamp DESC LIMIT 5
    """).fetchall()
    ok(f"按时间排序 Top5：")
    for r in rows_time:
        print(f"      [{r['post_id']}] @{r['username']} likes={r['likes_count']}  {r['content'][:30]}…")

    # 按人气
    rows_pop = conn.execute("""
        SELECT p.post_id, u.username, p.likes_count, p.content
        FROM posts p JOIN users u ON p.user_id = u.user_id
        ORDER BY p.likes_count DESC LIMIT 5
    """).fetchall()
    ok(f"按人气排序 Top5：")
    for r in rows_pop:
        print(f"      [{r['post_id']}] @{r['username']} likes={r['likes_count']}  {r['content'][:30]}…")

    # 人气最高的帖子点赞数应 >= 2
    top_likes = rows_pop[0]["likes_count"]
    if top_likes >= 2:
        ok(f"人气最高帖子点赞数 = {top_likes} ✓")
    else:
        fail(f"人气最高帖子点赞数异常: {top_likes}")

# ──────────────────────────────────────────────
# 测试 6：用户历史帖子
# ──────────────────────────────────────────────
def test_user_history(conn):
    section("TEST 6 — 用户历史帖子")
    rows = conn.execute("""
        SELECT p.post_id, p.content, p.likes_count
        FROM posts p JOIN users u ON p.user_id = u.user_id
        WHERE u.username = 'alice'
        ORDER BY p.timestamp DESC
    """).fetchall()
    assert_eq("alice 的帖子数", len(rows), 2)
    ok("alice 的帖子：")
    for r in rows:
        print(f"      [{r['post_id']}] likes={r['likes_count']}  {r['content'][:40]}")

# ──────────────────────────────────────────────
# 测试 7：外键级联删除
# ──────────────────────────────────────────────
def test_cascade(conn):
    section("TEST 7 — 外键级联删除")
    conn.execute("PRAGMA foreign_keys = ON")

    # 插入临时用户和帖子
    conn.execute("INSERT INTO users (username) VALUES ('temp_user')")
    conn.commit()
    temp_uid = conn.execute("SELECT user_id FROM users WHERE username='temp_user'").fetchone()[0]

    conn.execute("INSERT INTO posts (user_id, content) VALUES (?, '临时帖子')", (temp_uid,))
    conn.commit()
    temp_pid = conn.execute("SELECT post_id FROM posts WHERE user_id=?", (temp_uid,)).fetchone()[0]

    conn.execute("INSERT INTO likes  (user_id, post_id) VALUES (1, ?)", (temp_pid,))
    conn.execute("INSERT INTO comments (user_id, post_id, content) VALUES (?, ?, '测试评论')", (temp_uid, temp_pid))
    conn.commit()

    # 删除用户，帖子/点赞/评论应级联删除
    conn.execute("DELETE FROM users WHERE user_id=?", (temp_uid,))
    conn.commit()

    post_exists = conn.execute("SELECT 1 FROM posts WHERE post_id=?", (temp_pid,)).fetchone()
    like_exists = conn.execute("SELECT 1 FROM likes WHERE post_id=?", (temp_pid,)).fetchone()
    comment_exists = conn.execute("SELECT 1 FROM comments WHERE user_id=?", (temp_uid,)).fetchone()

    assert_eq("帖子已级联删除", post_exists,    None)
    assert_eq("点赞已级联删除", like_exists,    None)
    assert_eq("评论已级联删除", comment_exists, None)

# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────
def main():
    check_only = "--check" in sys.argv

    if check_only:
        section("CHECK MODE — 仅验证现有数据")
        conn = get_conn()
    else:
        section("DEMO MODE — 重置并填充演示数据")
        reset_db()
        conn = get_conn()
        test_users(conn)
        test_posts(conn)
        test_likes(conn)
        test_comments(conn)

    test_feed(conn)
    test_user_history(conn)
    test_cascade(conn)

    conn.close()
    section("全部测试通过 🎉")
    print(f"\n  数据库位置: {DB_PATH}\n")

if __name__ == "__main__":
    main()
