import json
import re
import subprocess


_VERDICT_EMOJI = {
    "safe": "✅",
    "risky": "⚠️",
    "dangerous": "🚨",
    "unknown": "❓",
}


def llm_precheck(hook_input: dict, policy: str) -> dict:
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    tool_input_json = json.dumps(tool_input, ensure_ascii=False, indent=2)

    prompt = (
        "以下のポリシーに基づき、Claude Code のツール使用リクエストを審査してください。\n\n"
        f"## ポリシー\n{policy}\n\n"
        f"## 審査対象\nツール名: {tool_name}\n入力内容:\n{tool_input_json}\n\n"
        "## 出力形式\n"
        '以下の JSON のみを返してください（説明文は不要）:\n'
        '{"verdict": "safe|risky|dangerous", "reason": "判断理由を1〜2文で"}'
    )

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", "claude-haiku-4-5-20251001",
                "--output-format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
        stdout = result.stdout.strip()

        # Claude Code CLI wraps the response in a JSON envelope
        inner_text = ""
        try:
            outer = json.loads(stdout)
            inner_text = outer.get("result", "")
            if inner_text:
                return json.loads(inner_text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

        # Fallback: extract first {...} block containing "verdict".
        # Search inner_text (unescaped) first; fall back to raw stdout.
        for haystack in filter(None, [inner_text, stdout]):
            m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', haystack, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group())
                except json.JSONDecodeError:
                    continue

        return {"verdict": "unknown", "reason": "審査失敗: レスポンスの解析に失敗"}
    except subprocess.TimeoutExpired:
        return {"verdict": "unknown", "reason": "審査失敗: タイムアウト"}
    except Exception as e:
        return {"verdict": "unknown", "reason": f"審査失敗: {e}"}
