import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

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
                image_urls=[
                    "https://example.com/original-1.jpg",
                    "https://example.com/original-2.jpg",
                ],
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
                image_urls=[
                    "https://example.com/updated-1.jpg",
                    "https://example.com/updated-2.jpg",
                    "https://example.com/updated-3.jpg",
                ],
            ),
        )

        self.assertEqual(response["message"], "Post updated successfully")

        posts = social_app.get_user_posts("alice")
        self.assertEqual(posts[0]["text_content"], "updated content")
        self.assertEqual(posts[0]["image_url"], "https://example.com/updated-1.jpg")
        self.assertEqual(
            posts[0]["image_urls"],
            [
                "https://example.com/updated-1.jpg",
                "https://example.com/updated-2.jpg",
                "https://example.com/updated-3.jpg",
            ],
        )

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


class AnalyticsRankingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = social_app.DB_PATH
        social_app.DB_PATH = str(Path(self.temp_dir.name) / "test_social_app.db")
        social_app.init_db()

        for username in ["alice", "bob", "carol", "david"]:
            social_app.create_user(social_app.CreateUser(username=username))

        social_app.create_post(social_app.CreatePost(username="alice", content="Alice post 1"))
        social_app.create_post(social_app.CreatePost(username="alice", content="Alice post 2"))
        social_app.create_post(social_app.CreatePost(username="bob", content="Bob post 1"))
        social_app.create_post(social_app.CreatePost(username="carol", content="Carol post 1"))

        like_pairs = [
            ("bob", 1),
            ("carol", 1),
            ("david", 1),
            ("alice", 2),
            ("bob", 2),
            ("alice", 3),
        ]
        for username, post_id in like_pairs:
            social_app.toggle_like(social_app.ToggleLike(username=username, post_id=post_id))

        comments = [
            ("bob", 1, "Great post"),
            ("carol", 1, "Same here"),
            ("david", 1, "Nice one"),
            ("alice", 3, "Replying on Bob post"),
            ("carol", 3, "Another Bob thread comment"),
            ("bob", 2, "Comment on Alice second post"),
        ]
        for username, post_id, content in comments:
            social_app.create_comment(
                social_app.CreateComment(
                    username=username,
                    post_id=post_id,
                    content=content,
                )
            )

    def tearDown(self):
        social_app.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_rankings_endpoint_returns_expected_podiums(self):
        rankings = social_app.get_rankings(limit=3)

        self.assertEqual(
            rankings["summary"],
            {
                "total_users": 4,
                "total_posts": 4,
                "total_comments": 6,
                "total_likes": 6,
            },
        )

        self.assertEqual([post["id"] for post in rankings["most_liked_posts"]], [1, 2, 3])
        self.assertEqual(rankings["most_liked_posts"][0]["like_count"], 3)
        self.assertEqual(rankings["most_liked_posts"][0]["comment_count"], 3)

        self.assertEqual([user["username"] for user in rankings["most_active_users"]], ["alice", "bob", "carol"])
        self.assertEqual(rankings["most_active_users"][0]["post_count"], 2)
        self.assertEqual(rankings["most_active_users"][1]["comment_count"], 2)

        self.assertEqual([post["id"] for post in rankings["most_discussed_posts"]], [1, 3, 2])
        self.assertEqual(rankings["most_discussed_posts"][1]["comment_count"], 2)


class FeedSortingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = social_app.DB_PATH
        social_app.DB_PATH = str(Path(self.temp_dir.name) / "test_social_app.db")
        social_app.init_db()

        for username in ["alice", "bob", "carol"]:
            social_app.create_user(social_app.CreateUser(username=username))

        social_app.create_post(social_app.CreatePost(username="alice", content="first post"))
        social_app.create_post(social_app.CreatePost(username="bob", content="second post"))
        social_app.create_post(social_app.CreatePost(username="carol", content="third post"))

        social_app.toggle_like(social_app.ToggleLike(username="bob", post_id=1))
        social_app.toggle_like(social_app.ToggleLike(username="carol", post_id=1))
        social_app.toggle_like(social_app.ToggleLike(username="alice", post_id=2))

    def tearDown(self):
        social_app.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_feed_can_sort_by_time_in_both_directions(self):
        newest_first = social_app.get_feed(sort="time", sort_order="desc")
        oldest_first = social_app.get_feed(sort="time", sort_order="asc")

        self.assertEqual([post["id"] for post in newest_first], [3, 2, 1])
        self.assertEqual([post["id"] for post in oldest_first], [1, 2, 3])

    def test_feed_can_sort_by_popularity_in_both_directions(self):
        most_liked_first = social_app.get_feed(sort="popularity", sort_order="desc")
        least_liked_first = social_app.get_feed(sort="popularity", sort_order="asc")

        self.assertEqual([post["id"] for post in most_liked_first], [1, 2, 3])
        self.assertEqual([post["id"] for post in least_liked_first], [3, 2, 1])


class ImageUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = social_app.DB_PATH
        self.original_uploads_dir = social_app.UPLOADS_DIR
        self.original_upload_images_dir = social_app.UPLOAD_IMAGES_DIR

        social_app.DB_PATH = str(Path(self.temp_dir.name) / "test_social_app.db")
        social_app.UPLOADS_DIR = str(Path(self.temp_dir.name) / "uploads")
        social_app.UPLOAD_IMAGES_DIR = str(Path(social_app.UPLOADS_DIR) / "images")
        Path(social_app.UPLOAD_IMAGES_DIR).mkdir(parents=True, exist_ok=True)

        social_app.init_db()
        social_app.create_user(social_app.CreateUser(username="alice"))
        self.client = TestClient(social_app.app)

    def tearDown(self):
        social_app.DB_PATH = self.original_db_path
        social_app.UPLOADS_DIR = self.original_uploads_dir
        social_app.UPLOAD_IMAGES_DIR = self.original_upload_images_dir
        self.temp_dir.cleanup()

    def test_upload_images_endpoint_is_disabled(self):
        response = self.client.post(
            "/api/uploads/images",
            files=[
                ("files", ("first.png", b"fake-image-1", "image/png")),
                ("files", ("second.jpg", b"fake-image-2", "image/jpeg")),
            ],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("https image URLs", response.json()["detail"])

    def test_create_post_accepts_and_preserves_https_image_urls(self):
        social_app.create_post(
            social_app.CreatePost(
                username="alice",
                content="remote images",
                image_urls=[
                    "https://example.com/example.png",
                    "https://cdn.example.org/second.webp",
                ],
            )
        )

        posts = social_app.get_user_posts("alice")
        self.assertEqual(
            posts[0]["image_urls"],
            [
                "https://example.com/example.png",
                "https://cdn.example.org/second.webp",
            ],
        )
        self.assertEqual(posts[0]["image_url"], "https://example.com/example.png")

    def test_upload_image_from_url_returns_same_https_url(self):
        response = self.client.post(
            "/api/uploads/image-url",
            json={"image_url": "https://example.com/sample.png"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["uploaded_url"], "https://example.com/sample.png")
        self.assertEqual(payload["uploaded_urls"], ["https://example.com/sample.png"])

    def test_upload_image_from_url_rejects_non_https_urls(self):
        response = self.client.post(
            "/api/uploads/image-url",
            json={"image_url": "http://example.com/not-secure.png"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("https image URLs", response.json()["detail"])

    def test_create_post_rejects_http_image_urls(self):
        with self.assertRaises(HTTPException) as context:
            social_app.create_post(
                social_app.CreatePost(
                    username="alice",
                    content="bad remote url",
                    image_url="http://example.com/image.png",
                )
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("https image URLs", context.exception.detail)

    def test_create_post_rejects_local_file_paths(self):
        with self.assertRaises(HTTPException) as context:
            social_app.create_post(
                social_app.CreatePost(
                    username="alice",
                    content="bad image path",
                    image_url="file:///Users/example/Desktop/test.png",
                )
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Local filesystem image paths", context.exception.detail)


if __name__ == "__main__":
    unittest.main()