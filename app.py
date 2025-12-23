"""
Quota Tracker TUI

README
------
Install: pip install textual pyinstaller
Run: python app.py
Build executable: pyinstaller --onefile --name quota app.py
"""

from __future__ import annotations

import calendar
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TextArea,
)

DB_PATH = Path(__file__).with_name("quota.db")

DEFAULT_TEMPLATE = [
    {
        "id": "progress",
        "text": "Progress: move a project forward",
        "importance": 3,
        "subitems": [],
    },
    {
        "id": "care",
        "text": "Care/Connection: serve or connect",
        "importance": 2,
        "subitems": [],
    },
    {
        "id": "maintenance",
        "text": "Maintenance: body / admin / environment",
        "importance": 2,
        "subitems": [],
    },
]

# -----------------
# Database utilities
# -----------------


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS template (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS day_item (
                day TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_text TEXT NOT NULL,
                importance INTEGER NOT NULL,
                checked INTEGER NOT NULL DEFAULT 0,
                evidence TEXT,
                why TEXT,
                checked_at TEXT,
                PRIMARY KEY (day, item_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS day_status (
                day TEXT PRIMARY KEY,
                closed INTEGER NOT NULL DEFAULT 0,
                closed_at TEXT
            )
            """
        )
        cur.execute("SELECT COUNT(*) FROM template")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO template (id, data) VALUES (1, ?)", (json.dumps(DEFAULT_TEMPLATE),))
        conn.commit()


def load_template() -> List[Dict]:
    with get_db() as conn:
        cur = conn.execute("SELECT data FROM template WHERE id = 1")
        row = cur.fetchone()
        if not row:
            return DEFAULT_TEMPLATE.copy()
        try:
            data = json.loads(row["data"])
            if not isinstance(data, list):
                raise ValueError
            return data
        except Exception:
            return DEFAULT_TEMPLATE.copy()


def save_template(template_data: List[Dict]) -> None:
    # Basic validation
    if not isinstance(template_data, list):
        raise ValueError("Template must be a list")
    for item in template_data:
        if not isinstance(item, dict) or "id" not in item or "text" not in item:
            raise ValueError("Each item must have id and text")
        item.setdefault("importance", 1)
        item.setdefault("subitems", [])
    with get_db() as conn:
        conn.execute("UPDATE template SET data = ? WHERE id = 1", (json.dumps(template_data),))
        conn.commit()


def _flatten_template(template_data: Sequence[Dict]) -> List[Dict]:
    flat: List[Dict] = []
    for item in template_data:
        base_id = str(item.get("id"))
        flat.append(
            {
                "item_id": base_id,
                "item_text": item.get("text", str(base_id)),
                "importance": int(item.get("importance", 1)),
            }
        )
        for sub in item.get("subitems", []) or []:
            sub_id = f"{base_id}:{sub.get('id', len(flat))}"
            flat.append(
                {
                    "item_id": sub_id,
                    "item_text": sub.get("text", str(sub_id)),
                    "importance": int(sub.get("importance", item.get("importance", 1))),
                }
            )
    return flat


def instantiate_day_if_needed(day: date) -> None:
    day_str = day.isoformat()
    with get_db() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM day_item WHERE day = ?", (day_str,))
        if cur.fetchone()[0] > 0:
            return
        template_data = load_template()
        flat = _flatten_template(template_data)
        for row in flat:
            conn.execute(
                """
                INSERT OR IGNORE INTO day_item (day, item_id, item_text, importance, checked, evidence, why, checked_at)
                VALUES (?, ?, ?, ?, 0, '', '', NULL)
                """,
                (day_str, row["item_id"], row["item_text"], row["importance"]),
            )
        conn.commit()


def get_day_items(day: date) -> List[sqlite3.Row]:
    instantiate_day_if_needed(day)
    day_str = day.isoformat()
    with get_db() as conn:
        cur = conn.execute(
            "SELECT * FROM day_item WHERE day = ? ORDER BY item_id",
            (day_str,),
        )
        return cur.fetchall()


def set_item_checked(day: date, item_id: str, checked: bool, evidence: str, why: str) -> None:
    if checked and not evidence.strip():
        raise ValueError("Evidence is required")
    with get_db() as conn:
        conn.execute(
            """
            UPDATE day_item
            SET checked = ?, evidence = ?, why = ?, checked_at = CASE WHEN ? = 1 THEN ? ELSE NULL END
            WHERE day = ? AND item_id = ?
            """,
            (
                1 if checked else 0,
                evidence.strip(),
                why.strip(),
                1 if checked else 0,
                datetime.now().isoformat(timespec="seconds") if checked else None,
                day.isoformat(),
                item_id,
            ),
        )
        conn.commit()


def get_checked_days(month_start: date, month_end: date) -> set[str]:
    with get_db() as conn:
        cur = conn.execute(
            """
            SELECT DISTINCT day FROM day_item
            WHERE day BETWEEN ? AND ? AND checked = 1
            """,
            (month_start.isoformat(), month_end.isoformat()),
        )
        return {row[0] for row in cur.fetchall()}


def is_day_closed(day: date) -> bool:
    with get_db() as conn:
        cur = conn.execute("SELECT closed FROM day_status WHERE day = ?", (day.isoformat(),))
        row = cur.fetchone()
        return bool(row[0]) if row else False


def set_day_closed(day: date, closed: bool) -> None:
    with get_db() as conn:
        if closed:
            conn.execute(
                "INSERT INTO day_status (day, closed, closed_at) VALUES (?, 1, ?) ON CONFLICT(day) DO UPDATE SET closed = 1, closed_at = excluded.closed_at",
                (day.isoformat(), datetime.now().isoformat(timespec="seconds")),
            )
        else:
            conn.execute(
                "INSERT INTO day_status (day, closed, closed_at) VALUES (?, 0, NULL) ON CONFLICT(day) DO UPDATE SET closed = 0, closed_at = NULL",
                (day.isoformat(),),
            )
        conn.commit()


# -------------
# UI Components
# -------------


class DaySelected(Message):
    def __init__(self, sender, day: date) -> None:
        self.day = day
        super().__init__(sender)


class QuotaClicked(Message):
    def __init__(self, sender, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(sender)


class QuotaItemView(Static):
    def __init__(self, item: sqlite3.Row, closed: bool) -> None:
        self.item = item
        self.closed = closed
        super().__init__()

    def render(self) -> str:
        checkbox = "✅" if self.item["checked"] else "⬜"
        base = f"{checkbox} {self.item['item_text']} (importance {self.item['importance']})"
        if self.item["checked"]:
            evidence = self.item["evidence"] or ""
            why = self.item["why"] or ""
            extra = f"\n  Evidence: {evidence}"
            if why:
                extra += f"\n  Why: {why}"
            return base + extra
        return base

    def on_click(self, event: events.Click) -> None:  # type: ignore[override]
        event.stop()
        self.post_message(QuotaClicked(self, self.item["item_id"]))


class CalendarView(Vertical):
    month: reactive[date] = reactive(date.today())
    selected_day: reactive[date] = reactive(date.today())

    def __init__(self) -> None:
        super().__init__(id="calendar")
        self.checked_days: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Button("⏴ Prev", id="prev"),
            Button("Today", id="today"),
            Button("Next ⏵", id="next"),
            id="nav",
        )
        yield Label("", id="month_label")
        yield Container(id="days")

    def on_mount(self) -> None:
        self.refresh_calendar()

    def set_checked_days(self, days: set[str]) -> None:
        self.checked_days = days
        self.refresh_calendar()

    def refresh_calendar(self) -> None:
        month_label = self.query_one("#month_label", Label)
        month_label.update(self.month.strftime("%B %Y"))
        days_container = self.query_one("#days", Container)
        days_container.remove_children()

        first_weekday, num_days = calendar.monthrange(self.month.year, self.month.month)
        day_grid: List[Static] = []
        # pad
        for _ in range(first_weekday):
            day_grid.append(Static("", classes="empty"))
        for day_num in range(1, num_days + 1):
            day_date = date(self.month.year, self.month.month, day_num)
            marker = "•" if day_date.isoformat() in self.checked_days else ""
            text = f"{day_num:2d} {marker}"
            btn = Button(text, id=f"day-{day_num}")
            if day_date == self.selected_day:
                btn.add_class("selected")
            btn.tooltip = day_date.isoformat()
            day_grid.append(btn)
        grid_container = Container(*day_grid, id="day-grid")
        days_container.mount(grid_container)

    def watch_month(self, old: date, new: date) -> None:  # type: ignore[override]
        month_start = new.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        self.checked_days = get_checked_days(month_start, month_end)
        self.refresh_calendar()

    def watch_selected_day(self, old: date, new: date) -> None:  # type: ignore[override]
        self.refresh_calendar()

    def action_prev(self) -> None:
        new_month = (self.month.replace(day=1) - timedelta(days=1)).replace(day=1)
        self.month = new_month

    def action_next(self) -> None:
        next_month = (self.month.replace(day=28) + timedelta(days=4)).replace(day=1)
        self.month = next_month

    def action_today(self) -> None:
        today = date.today()
        self.month = today.replace(day=1)
        self.selected_day = today
        self.post_message(DaySelected(self, today))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev":
            self.action_prev()
        elif event.button.id == "next":
            self.action_next()
        elif event.button.id == "today":
            self.action_today()
        elif event.button.id and event.button.id.startswith("day-"):
            day_num = int(event.button.id.split("-")[1])
            selected = date(self.month.year, self.month.month, day_num)
            self.selected_day = selected
            self.post_message(DaySelected(self, selected))


class CheckModal(ModalScreen[Optional[Dict]]):
    def __init__(self, item: sqlite3.Row) -> None:
        super().__init__()
        self.item = item
        self.validation = Label("", classes="validation")

    def compose(self) -> ComposeResult:
        yield Static(f"{self.item['item_text']} (importance {self.item['importance']})", classes="modal-title")
        yield Label("Evidence (required)")
        yield Input(value=self.item["evidence"] or "", id="evidence")
        yield Label("Why (optional)")
        yield Input(value=self.item["why"] or "", id="why")
        yield self.validation
        yield Horizontal(
            Button("Check", id="check"),
            Button("Uncheck", id="uncheck"),
            Button("Cancel", id="cancel"),
            id="modal-actions",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        evidence_input = self.query_one("#evidence", Input)
        why_input = self.query_one("#why", Input)
        evidence = evidence_input.value
        why = why_input.value
        if event.button.id == "check":
            if not evidence.strip():
                self.validation.update("Evidence is required")
                return
            self.dismiss({"checked": True, "evidence": evidence, "why": why, "item_id": self.item["item_id"]})
        elif event.button.id == "uncheck":
            self.dismiss({"checked": False, "evidence": evidence, "why": why, "item_id": self.item["item_id"]})


class SettingsScreen(Screen):
    BINDINGS = [
        ("escape", "pop_screen", "Back"),
    ]

    def compose(self) -> ComposeResult:
        template_json = json.dumps(load_template(), indent=2)
        yield Header(show_clock=False)
        yield Vertical(
            Label("Edit template JSON (list of items with id, text, importance, subitems)"),
            TextArea(template_json, id="template-editor", language="json"),
            Horizontal(
                Button("Save", id="save"),
                Button("Reset to Default", id="reset"),
                Button("Back", id="back"),
            ),
            id="settings-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
            return
        if event.button.id == "reset":
            try:
                save_template(json.loads(json.dumps(DEFAULT_TEMPLATE)))
                self.query_one("#template-editor", TextArea).value = json.dumps(DEFAULT_TEMPLATE, indent=2)
                self.app.notify("Template reset to default", severity="information")
            except Exception as exc:  # pragma: no cover - safety
                self.app.notify(f"Failed to reset: {exc}", severity="error")
            return
        if event.button.id == "save":
            editor = self.query_one("#template-editor", TextArea)
            try:
                parsed = json.loads(editor.value)
                save_template(parsed)
                self.app.notify("Template saved", severity="information")
            except Exception as exc:
                self.app.notify(f"Invalid template: {exc}", severity="error")


class MainScreen(Screen):
    def __init__(self) -> None:
        super().__init__()
        self.selected_day: date = date.today()
        self.items: List[sqlite3.Row] = []
        self.closed: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            CalendarView(),
            Vertical(
                Horizontal(
                    Label("", id="day-label"),
                    Button("Settings", id="settings"),
                    Button("Close Day", id="close-day"),
                    Button("Reopen Day", id="reopen-day", classes="hidden"),
                    id="top-actions",
                ),
                Container(id="items"),
                id="right-pane",
            ),
            id="layout",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.load_day(self.selected_day)

    def load_day(self, day: date) -> None:
        instantiate_day_if_needed(day)
        self.items = get_day_items(day)
        self.closed = is_day_closed(day)
        day_label = self.query_one("#day-label", Label)
        day_label.update(f"Selected: {day.isoformat()}" + (" (Closed)" if self.closed else ""))
        close_btn = self.query_one("#close-day", Button)
        reopen_btn = self.query_one("#reopen-day", Button)
        if self.closed:
            close_btn.add_class("hidden")
            reopen_btn.remove_class("hidden")
        else:
            reopen_btn.add_class("hidden")
            close_btn.remove_class("hidden")
        items_container = self.query_one("#items", Container)
        items_container.remove_children()
        for row in self.items:
            items_container.mount(QuotaItemView(row, self.closed))
        # update calendar markers
        cal = self.query_one(CalendarView)
        month_start = cal.month.replace(day=1)
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)
        cal.set_checked_days(get_checked_days(month_start, month_end))
        cal.selected_day = day
        cal.month = day.replace(day=1)

    def on_day_selected(self, message: DaySelected) -> None:
        self.selected_day = message.day
        self.load_day(message.day)

    def on_quota_clicked(self, message: QuotaClicked) -> None:
        if self.closed:
            self.app.notify("Day is closed. Reopen to edit.", severity="warning")
            return
        item = next((i for i in self.items if i["item_id"] == message.item_id), None)
        if not item:
            self.app.notify("Item not found", severity="error")
            return
        self.app.push_screen(CheckModal(item), self.handle_modal_result)

    def handle_modal_result(self, result: Optional[Dict]) -> None:
        if result is None:
            return
        item_id = result.get("item_id", "")
        if not item_id:
            self.app.notify("Missing item id", severity="error")
            return
        try:
            set_item_checked(
                self.selected_day,
                item_id,
                result["checked"],
                result.get("evidence", ""),
                result.get("why", ""),
            )
        except Exception as exc:
            self.app.notify(str(exc), severity="error")
        self.load_day(self.selected_day)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings":
            self.app.push_screen(SettingsScreen())
        elif event.button.id == "close-day":
            set_day_closed(self.selected_day, True)
            self.load_day(self.selected_day)
        elif event.button.id == "reopen-day":
            set_day_closed(self.selected_day, False)
            self.load_day(self.selected_day)


class QuotaApp(App):
    CSS = """
    #layout { height: 1fr; }
    #calendar { width: 30%; min-width: 30w; padding: 1; border: solid $accent; }
    #right-pane { padding: 1; }
    #day-grid { grid-size: 7; grid-gutter: 1 1; }
    Button.selected { background: $accent; color: $text; }
    .hidden { display: none; }
    #items > * { padding: 1; border: solid $panel; margin: 0 0 1 0; }
    .validation { color: $warning; }
    #modal-actions Button { width: 1fr; }
    #settings-container TextArea { height: 20; }
    """

    TITLE = "Quota Tracker"
    SUB_TITLE = "Minimal daily checklist"

    def on_mount(self) -> None:
        init_db()
        self.push_screen(MainScreen())


if __name__ == "__main__":
    app = QuotaApp()
    app.run()
