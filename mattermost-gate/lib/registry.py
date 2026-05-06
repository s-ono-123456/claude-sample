import json
import os
import uuid as _uuid

_REGISTRY_ROOT = os.path.join(os.path.dirname(__file__), "..", "tmp")


def create_entry(session_id: str, tool_name: str, post_id: str) -> str:
    entry_dir = os.path.join(_REGISTRY_ROOT, session_id)
    os.makedirs(entry_dir, exist_ok=True)
    key = str(_uuid.uuid4())
    with open(os.path.join(entry_dir, f"{key}.json"), "w", encoding="utf-8") as f:
        json.dump({"tool_name": tool_name, "post_id": post_id}, f)
    return key


def delete_entry(session_id: str, key: str) -> None:
    try:
        os.unlink(os.path.join(_REGISTRY_ROOT, session_id, f"{key}.json"))
    except FileNotFoundError:
        pass


def find_by_tool(session_id: str, tool_name: str) -> list[tuple[str, str]]:
    return _scan(session_id, tool_name_filter=tool_name)


def find_all(session_id: str) -> list[tuple[str, str]]:
    return _scan(session_id)


def _scan(session_id: str, tool_name_filter: str | None = None) -> list[tuple[str, str]]:
    entry_dir = os.path.join(_REGISTRY_ROOT, session_id)
    if not os.path.exists(entry_dir):
        return []
    results = []
    for fname in os.listdir(entry_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(entry_dir, fname), encoding="utf-8") as f:
                data = json.load(f)
            if tool_name_filter is None or data.get("tool_name") == tool_name_filter:
                results.append((fname[:-5], data["post_id"]))
        except Exception:
            pass
    return results
