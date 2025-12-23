# AGENTS.md — Quota TUI App

This file defines **non-negotiable constraints and working rules** for humans and AI agents contributing to this project.

This app exists to reduce cognitive friction, preserve autonomy, and manufacture *evidence of progress* — not to become a productivity product.

If a change violates the spirit or letter of this file, it is wrong even if it “works.”

---

## 1. Project Purpose (Read This First)

This is a **local-first terminal application** that helps a single user:
- define a small daily quota,
- complete items with *evidence*,
- close the day cleanly,
- and avoid moralized productivity systems.

Success criteria:
- Low friction
- Fast startup
- Clear closure
- Zero guilt mechanics

This app is **not**:
- a habit tracker
- a streak system
- a dashboard
- a gamified tool
- a cloud service
- a social product

---

## 2. MVP Scope Fence (Hard Boundary)

### In Scope (MVP)
- Terminal UI (Textual)
- Dual-pane layout:
  - Calendar (month view)
  - Day quota view
- Daily quota items
- Required **Evidence** to check an item
- Optional **Why**
- SQLite persistence
- Day Close / Reopen
- Settings to edit the quota template
- Local packaging (PyInstaller)

### Explicitly Out of Scope (Until Further Notice)
- Streaks
- Analytics
- Charts
- Tags
- Notifications
- Sync / cloud
- User accounts
- Gamification
- AI suggestions
- Theming
- Plugins
- Infinite configuration

If an agent proposes any of the above, **reject the change**.

---

## 3. Architectural Rules

### Layering (Mandatory)
- **UI layer**: rendering + event handling only  
  ❌ No SQL  
  ❌ No business logic
- **Logic layer**: pure functions
- **Persistence layer**: SQLite access only

UI code must call logic functions, which call persistence.

---

### File Structure (Target, not immediate)
```
app.py            # entry point
db.py             # SQLite access
models.py         # dataclasses / domain models
logic.py          # business rules (pure)
ui/               # Textual screens & widgets
```

Single-file MVP is allowed, but logic must still be separable.

---

## 4. Data Integrity Rules

- **Never delete** historical data.
- Past days must remain immutable unless explicitly reopened.
- Template changes **do not retroactively alter past days**.
- Evidence must be non-empty:
  - Enforced in UI
  - Enforced in logic
  - Enforced in DB constraints where possible

SQLite schema changes require:
- schema versioning
- idempotent migrations

---

## 5. “Day Closed” Semantics (Critical)

- A closed day is **read-only**
- UI must block edits and explain why
- Reopening a day requires explicit user action
- Closing a day must feel *final*, not cosmetic

This is about psychological closure, not aesthetics.

---

## 6. UX / Friction Principles

This app exists to reduce friction, not add it.

### Mandatory UX Constraints
- App startup < 1 second on normal hardware
- Keyboard-only operation must be possible
- Mouse support is optional, not required
- Default “check item” flow ≤ 3 interactions:
  - select item → enter evidence → confirm

### Language Rules
- No moral language
- No shame
- No “you should”
- Neutral, factual UI copy only

---

## 7. Testing Contract

Any change that affects:
- persistence
- business logic
- day state
must include tests.

### Testing Rules
- Use `pytest`
- DB tests must use temp DB or `:memory:`
- Tests must be deterministic
- UI tests are optional; logic tests are not

No tests → no merge.

---

## 8. Performance & Safety

- Avoid unbounded queries
- Paginate any future list views
- Treat all user input as untrusted strings
- Never execute or eval evidence text
- No background threads unless explicitly justified

---

## 9. Packaging & Local-First Rules

- App must run via: `python app.py`
- Packaging via PyInstaller is supported
- App must work fully offline
- No telemetry
- No auto-updates

User data belongs to the user, locally.

---

## 10. AI Agent Workflow Rules (Strict)

When an AI agent contributes code, it **must**:

1. Provide a short plan (≤ 8 bullets)
2. Make only the requested change
3. Avoid refactors unless explicitly asked
4. Avoid adding dependencies unless justified
5. Output code diffs or full files
