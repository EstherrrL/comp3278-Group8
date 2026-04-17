import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import app as social_app


class CreateUserTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = social_app.DB_PATH
        social_app.DB_PATH = str(Path(self.temp_dir.name) / "test_social_app.db")
        social_app.init_db()

    def tearDown(self):
        social_app.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_duplicate_username_returns_conflict(self):
        response = social_app.create_user(social_app.CreateUser(username="alice"))

        self.assertEqual(response["message"], "User created successfully")

        with self.assertRaises(HTTPException) as context:
            social_app.create_user(social_app.CreateUser(username="alice"))

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail, "Username already exists")

    def test_user_persists_after_reinitializing_app(self):
        social_app.create_user(social_app.CreateUser(username="persistent_user"))

        social_app.init_db()

        users = social_app.get_users()
        self.assertIn("persistent_user", users)


class PostOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = social_app.DB_PATH
        social_app.DB_PATH = str(Path(self.temp_dir.name) / "test_social_app.db")
        social_app.init_db()

        social_app.create_user(social_app.CreateUser(username="alice"))
        social_app.create_user(social_app.CreateUser(username="bob"))
        social_app.create_post(
            social_app.CreatePost(
                username="alice",
                content="original content",
                image_url="https://example.com/original.jpg",
            )
        )

    def tearDown(self):
        social_app.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_author_can_update_own_post(self):
        response = social_app.update_post(
            1,
            social_app.UpdatePost(
                username="alice",
                content="updated content",
                image_url="https://example.com/updated.jpg",
            ),
        )

        self.assertEqual(response["message"], "Post updated successfully")

        posts = social_app.get_user_posts("alice")
        self.assertEqual(posts[0]["text_content"], "updated content")
        self.assertEqual(posts[0]["image_url"], "https://example.com/updated.jpg")

    def test_non_author_cannot_update_someone_elses_post(self):
        with self.assertRaises(HTTPException) as context:
            social_app.update_post(
                1,
                social_app.UpdatePost(
                    username="bob",
                    content="hijacked content",
                    image_url=None,
                ),
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.detail, "You can only edit your own posts")

    def test_author_can_delete_own_post(self):
        response = social_app.delete_post(1, social_app.DeletePost(username="alice"))

        self.assertEqual(response["message"], "Post deleted successfully")
        self.assertEqual(social_app.get_user_posts("alice"), [])


if __name__ == "__main__":
    unittest.main()