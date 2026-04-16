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


if __name__ == "__main__":
    unittest.main()