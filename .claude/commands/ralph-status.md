# Ralph Status — Gold Tier Skill

Check the status of the Ralph Wiggum autonomous task chain loop, view queued chains, and manage the loop counter.

## Usage

```
/ralph-status           ← Show current loop state and queued chains
/ralph-status reset     ← Reset the loop counter (if stuck)
/ralph-status stop      ← Create STOP.md to halt all autonomous actions
/ralph-status resume    ← Remove STOP.md to resume autonomous actions
```

## What is Ralph?

The Ralph Wiggum Loop is the autonomous task-chaining system that keeps Claude working until everything is done.

**Two components:**
1. **`scripts/ralph_check.py`** — Claude Code Stop Hook: runs after every Claude response, detects pending work, blocks Claude from stopping if more tasks exist
2. **`watchers/ralph_watcher.py`** — Background daemon: watches Done/ files for `next_action:` fields and auto-creates follow-up tasks

## Instructions for `/ralph-status`

1. Check `AI_Employee_Vault/STOP.md` — if exists, Ralph is halted.
2. Read `.ralph_loop_count` from the project root — current loop count (max 5).
3. Count Done/ files with `next_action:` frontmatter that haven't been processed yet.
4. Count Needs_Action/ files with `auto_execute: true` frontmatter.
5. Count Pending_Approval/ files with `auto_approve: true` frontmatter.
6. Report status:

```
Ralph Wiggum Loop Status — 2026-03-11 10:00

Status:        ACTIVE (running)
Loop counter:  2 / 5
STOP.md:       not present

Queued chains:
  ✓ 0 Done/ files with next_action pending

Auto-execute tasks:
  ✓ 0 Needs_Action/ files with auto_execute: true

Pending items:
  - 1 Pending_Approval/ file awaiting human review

Ralph Watcher: check with `ps aux | grep ralph_watcher`
```

## Instructions for `/ralph-status reset`

1. Delete `.ralph_loop_count` from project root.
2. Report: "Ralph loop counter reset to 0."

## Instructions for `/ralph-status stop`

1. Write `AI_Employee_Vault/STOP.md` with content: `STOP — halted by user at <timestamp>`
2. Report: "Emergency stop activated. All autonomous actions halted. Run `/ralph-status resume` to restart."

## Instructions for `/ralph-status resume`

1. Check if `AI_Employee_Vault/STOP.md` exists.
2. Delete it.
3. Report: "STOP.md removed. Autonomous actions resumed."

## Task Chaining Pattern

To chain tasks, add `next_action:` to any Done/ file:

```yaml
---
type: email_response
status: done
completed: 2026-03-11T10:00:00Z
next_action: Send follow-up invoice to client
---
```

Ralph Watcher detects this and creates:
`Needs_Action/RALPH_CHAIN_<timestamp>.md` automatically.

## Loop Counter

Ralph stops looping after 5 iterations per Claude session (prevents infinite loops).
Reset with `/ralph-status reset` if needed.

## Troubleshooting

- **Ralph not looping**: Check `.claude.json` has the Stop hook configured
- **Loop stuck at max**: Run `/ralph-status reset`
- **Watcher not running**: `python watchers/ralph_watcher.py` in a terminal
