---
name: session-retro
description: |
  Analyze the current session's conversation history and produce a structured retrospective report in Markdown. Covers token efficiency, approval flow quality, CLAUDE.md improvement suggestions, skill extraction opportunities, and an overall summary.

  Invoke this skill whenever the user asks for a session review or retrospective. Trigger phrases include: "セッション振り返り", "振り返りをして", "振り返り", "session retro", "retrospective", "このセッションを振り返って", "今回のセッションどうだった". Also trigger when the user asks how the session could have been more efficient, whether approval requests were clear, or what could be scripted or turned into a skill. Don't wait for the exact phrase — if the intent is to reflect on what happened in this session and how to improve, use this skill.
---

# Session Retrospective

Review the conversation from the beginning of this session and produce the report below. Output the report to the user as Markdown AND save it to `retro/YYYY-MM-DD.md` under the current working directory (e.g. `C:\claude\retro\2026-05-06.md`). If a file with that name already exists, append `-2`, `-3`, etc. Create the `retro/` directory if it does not exist. Use the Write tool to save the file.

Examine actual exchanges concretely before drawing conclusions. Cite specific moments ("at the X step, Claude proposed a custom script for Y...") rather than giving generic advice. If a section has nothing notable, write "特になし" and move on — don't pad.

## Report template

Use this structure exactly:

---

# セッション振り返りレポート

**日時**: [today's date]
**主なタスク**: [one-sentence summary of what was accomplished]

---

## 1. トークン効率

**非効率なパターン**

Look for these specific anti-patterns and cite where they occurred:
- 同じファイルや情報を複数回読み直した
- 計画を立てた後、すでに合意済みの内容を再確認するやり取りが発生した
- ユーザが求めていない中間出力（詳細なログ・長い説明）を生成した
- 文脈から推測できることをあえて確認した

**良かった点**

- [Efficient patterns that avoided waste]

**改善提案**

- [Specific changes — e.g., "最初に X を確認しておけば Y の往復が不要だった"]

---

## 2. 承認フロー品質

The user's key concern: approval requests that require reviewing unfamiliar code logic are high-burden. Pre-defined skills, CLAUDE.md-sanctioned scripts, and built-in tools are low-burden. Custom scripts proposed ad-hoc are high-burden.

**承認負荷が高かった箇所**

- [Specific instances where the user had to evaluate code content, not just purpose]
- [Cases where Claude proposed a custom script or undefined tool that required the user to understand implementation details]
- [Approvals where the purpose wasn't clear from the request alone]

**事前定義スクリプト・スキルへの置換可能性**

- [Where a pre-defined skill or CLAUDE.md-listed script could have replaced the ad-hoc approach, reducing review burden]

**良かった点**

- [Clear, purposeful approval requests that the user could evaluate quickly]

---

## 3. CLAUDE.md 改善提案

Look for moments where a rule in CLAUDE.md — or the absence of one — caused rework, extra confirmation rounds, or misunderstanding. Propose concrete additions or clarifications.

| 問題 | 提案するルール |
|------|--------------|
| [What happened] | [Exact wording to add/clarify in CLAUDE.md] |

特になし → そのまま記載。

---

## 4. スキル化提案

Identify workflows that were executed in this session that could benefit from being a skill — either because they'll recur, or because wrapping them in a skill would reduce approval burden (pre-defined = low-burden).

| パターン | スキル名候補 | 理由 | 優先度 |
|---------|------------|------|--------|
| [Pattern] | [skill-name] | [Why this would help] | 高/中/低 |

特になし → そのまま記載。

---

## 5. 総括

**良かった点** (2–3 bullets max)
- [What worked well]

**改善点** (2–3 bullets max)
- [What to do differently]

**次セッションへの推奨アクション**
1. [Highest-priority actionable item]
2. [Second item if needed]

---

## Notes for the analyst (you)

- Be specific and honest. A retrospective that only says "things went well" is useless. Surface real friction, even if minor.
- Approval burden is about cognitive load, not count. One confusing request is worse than five clear ones. Flag the confusing ones.
- For CLAUDE.md suggestions, write the proposed rule text precisely enough that the user could paste it in directly if they agree.
- For skill proposals, a pattern that appeared once but is likely to recur is worth noting at medium priority. Patterns that appeared twice or more warrant high priority.
- Keep the total report concise — the user reads this after a session and wants signal, not recap.
