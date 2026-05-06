#!/usr/bin/env python3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.mattermost import MattermostClient
from lib import registry

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    session_id = hook_input.get("session_id", "")
    if not session_id:
        sys.exit(0)

    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        sys.exit(0)

    entries = registry.find_all(session_id)
    if not entries:
        sys.exit(0)

    terminal_emoji = config.get("terminal_emoji", "computer")
    try:
        client = MattermostClient(config)
        bot_user_id = client.get_bot_user_id()
    except Exception:
        sys.exit(0)

    for key, post_id in entries:
        try:
            client.add_reaction(bot_user_id, post_id, terminal_emoji)
        except Exception:
            pass
        registry.delete_entry(session_id, key)


if __name__ == "__main__":
    main()
