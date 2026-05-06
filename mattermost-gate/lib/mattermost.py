import sys
import time

import requests


class MattermostClient:
    def __init__(self, config: dict):
        self._base = config["mattermost_url"].rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {config['token']}",
            "Content-Type": "application/json",
        }
        self._channel_id = config["channel_id"]
        self._approve_emoji = config.get("approve_emoji", "white_check_mark")
        self._deny_emoji = config.get("deny_emoji", "x")
        self._timeout = config.get("timeout_seconds", 300)
        self._interval = config.get("poll_interval_seconds", 2)

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def get_bot_user_id(self) -> str:
        resp = requests.get(self._url("/api/v4/users/me"), headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json()["id"]

    def post_message(self, message: str) -> str:
        payload = {"channel_id": self._channel_id, "message": message}
        resp = requests.post(self._url("/api/v4/posts"), headers=self._headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()["id"]

    def post_reply(self, root_id: str, message: str) -> str:
        payload = {"channel_id": self._channel_id, "message": message, "root_id": root_id}
        resp = requests.post(self._url("/api/v4/posts"), headers=self._headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()["id"]

    def add_reaction(self, user_id: str, post_id: str, emoji_name: str) -> None:
        payload = {"user_id": user_id, "post_id": post_id, "emoji_name": emoji_name}
        resp = requests.post(self._url("/api/v4/reactions"), headers=self._headers, json=payload, timeout=10)
        resp.raise_for_status()

    def get_reactions(self, post_id: str) -> list[dict]:
        resp = requests.get(self._url(f"/api/v4/posts/{post_id}/reactions"), headers=self._headers, timeout=10)
        resp.raise_for_status()
        return resp.json() or []

    def poll_for_decision(self, post_id: str, bot_user_id: str, terminal_emoji: str = "") -> str:
        deadline = time.time() + self._timeout
        while time.time() < deadline:
            try:
                reactions = self.get_reactions(post_id)
                all_names = {r["emoji_name"] for r in reactions}
                human_names = {r["emoji_name"] for r in reactions if r["user_id"] != bot_user_id}
                if self._approve_emoji in human_names:
                    return "allow"
                if self._deny_emoji in human_names:
                    return "deny"
                if terminal_emoji and terminal_emoji in all_names:
                    return "cancelled"
            except Exception as e:
                print(f"[mattermost-gate] polling error: {e}", file=sys.stderr)
            time.sleep(self._interval)

        return "timeout"

    def get_thread_replies(self, post_id: str) -> list[dict]:
        resp = requests.get(self._url(f"/api/v4/posts/{post_id}/thread"), headers=self._headers, timeout=10)
        resp.raise_for_status()
        posts = resp.json().get("posts", {})
        replies = [p for p in posts.values() if p.get("root_id") == post_id]
        replies.sort(key=lambda p: p.get("create_at", 0))
        return replies

    def poll_for_thread_reply(self, post_id: str, bot_user_id: str, timeout: int) -> str | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for reply in self.get_thread_replies(post_id):
                    if reply["user_id"] != bot_user_id:
                        return reply.get("message", "")
            except Exception as e:
                print(f"[mattermost-gate] thread reply polling error: {e}", file=sys.stderr)
            time.sleep(self._interval)
        return None
