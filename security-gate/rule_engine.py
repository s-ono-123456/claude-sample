import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import yaml


@dataclass
class MatchResult:
    rule_id: str
    description: str
    action: str
    matched_field: str
    matched_value: str


class ConditionChecker:
    @staticmethod
    def check_regex(value: str, pattern: str) -> bool:
        try:
            return bool(re.search(pattern, value, re.IGNORECASE))
        except re.error:
            return False

    @staticmethod
    def check_contains(value: str, substring: str) -> bool:
        return substring.lower() in value.lower()

    @staticmethod
    def check_path_match(value: str, patterns: list) -> bool:
        basename = os.path.basename(value)
        normalized = value.replace("\\", "/")
        for pat in patterns:
            pat_normalized = pat.replace("\\", "/")
            pat_basename = os.path.basename(pat_normalized.replace("**/", ""))
            if fnmatch.fnmatch(normalized, pat_normalized):
                return True
            # pat_basename が純粋なワイルドカード（** / * のみ）の場合は
            # basename マッチをスキップして誤マッチを防ぐ
            if pat_basename and not all(c in "*?" for c in pat_basename):
                if fnmatch.fnmatch(basename, pat_basename):
                    return True
        return False


class RuleEngine:
    def __init__(self, rules_path: str):
        self.rules_path = rules_path
        self._rules: list[dict] = []
        self._settings: dict = {}

    def load(self) -> None:
        try:
            with open(self.rules_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._rules = data.get("rules", [])
            self._settings = data.get("settings", {})
        except Exception as e:
            print(f"[security-gate] rules.yaml load error: {e}", file=sys.stderr)
            self._rules = []
            self._settings = {}

    @property
    def log_path(self) -> str:
        return self._settings.get(
            "log_path",
            os.path.join(os.path.dirname(self.rules_path), "log", "security.jsonl"),
        )

    def evaluate(self, tool_name: str, tool_input: dict) -> list[MatchResult]:
        results = []
        for rule in self._rules:
            if not rule.get("enabled", True):
                continue

            tools = rule.get("tools")
            if tools and tool_name not in tools:
                continue

            for condition in rule.get("conditions", []):
                field = condition.get("field", "")
                value = self._get_field_value(tool_input, field)
                if value is None:
                    continue

                matched = False
                ctype = condition.get("type", "regex")
                if ctype == "regex":
                    matched = ConditionChecker.check_regex(value, condition.get("pattern", ""))
                elif ctype == "contains":
                    matched = ConditionChecker.check_contains(value, condition.get("value", ""))
                elif ctype == "path_match":
                    matched = ConditionChecker.check_path_match(value, condition.get("paths", []))

                if matched:
                    results.append(MatchResult(
                        rule_id=rule.get("id", "unknown"),
                        description=rule.get("description", ""),
                        action=rule.get("action", "log"),
                        matched_field=field,
                        matched_value=value[:200],
                    ))
                    break  # 同一ルール内で最初にマッチした条件で確定

        return results

    def _get_field_value(self, tool_input: dict, field: str) -> str | None:
        val = tool_input.get(field)
        if val is None:
            return None
        return str(val)


class AuditLogger:
    def __init__(self, log_path: str):
        self.log_path = log_path

    def log(self, event: str, session_id: str, tool_name: str, result: MatchResult | None) -> None:
        record: dict = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "tool_name": tool_name,
        }
        if result:
            record["rule_id"] = result.rule_id
            record["description"] = result.description
            record["matched_field"] = result.matched_field
            record["matched_value"] = result.matched_value
        else:
            record["rule_id"] = None

        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[security-gate] audit write error: {e}", file=sys.stderr)
