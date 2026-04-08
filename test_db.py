import sqlite3

# 执行上面的建表 SQL（复制到变量里）
SCHEMA_SQL = """ CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts(
    post_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content TEXT,
    image_url TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    likes_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS likes(
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, post_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comments(
    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_posts_user_id ON posts(user_id);
CREATE INDEX idx_posts_timestamp ON posts(timestamp);
CREATE INDEX idx_posts_likes_count ON posts(likes_count);
CREATE INDEX idx_likes_post_id ON likes(post_id);
CREATE INDEX idx_comments_post_id ON comments(post_id); """

# 创建数据库
conn = sqlite3.connect("social_app.db")
conn.executescript(SCHEMA_SQL)
conn.commit()

# 插入测试数据
cursor = conn.cursor()
cursor.execute("INSERT INTO users (username) VALUES ('alice')")
cursor.execute("INSERT INTO posts (user_id, content) VALUES (1, 'Hello world!')")
cursor.execute("INSERT INTO likes (user_id, post_id) VALUES (1, 1)")
cursor.execute("INSERT INTO comments (user_id, post_id, content) VALUES (1, 1, 'Nice post!')")
conn.commit()

# 验证查询
print("用户列表:", cursor.execute("SELECT * FROM users").fetchall())
print("帖子列表:", cursor.execute("SELECT * FROM posts").fetchall())
print("点赞:", cursor.execute("SELECT * FROM likes").fetchall())
print("评论:", cursor.execute("SELECT * FROM comments").fetchall())

conn.close()
print("数据库测试通过！")