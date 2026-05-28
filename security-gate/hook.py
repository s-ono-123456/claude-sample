import json
import os
import sys

_RULES_DIR = os.path.join(os.path.dirname(__file__), "rules.d")

# rule_engine を同一ディレクトリから import
sys.path.insert(0, os.path.dirname(__file__))
from rule_engine import AuditLogger, RuleEngine


def main() -> None:
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except Exception as e:
        print(f"[security-gate] stdin parse error: {e}", file=sys.stderr)
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    session_id = hook_input.get("session_id", "")

    engine = RuleEngine(_RULES_DIR)
    engine.load()

    logger = AuditLogger(engine.log_path)
    results = engine.evaluate(tool_name, tool_input)

    # block ルールが1つでもマッチしたら即座にブロック
    for result in results:
        if result.action == "block":
            logger.log("block", session_id, tool_name, result)
            reason = f"[security-gate] BLOCK: {result.description} (rule: {result.rule_id})"
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": reason,
                        }
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(0)

    # log ルールのみマッチした場合はログに記録して通過
    for result in results:
        if result.action == "log":
            logger.log("log", session_id, tool_name, result)

    if not results:
        logger.log("pass", session_id, tool_name, None)

    sys.exit(0)


if __name__ == "__main__":
    main()
