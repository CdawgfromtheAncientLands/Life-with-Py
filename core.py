from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

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


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn


class TemplateRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def init_schema(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS template (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    data TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def ensure_default(self) -> None:
        with self.db.connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM template")
            if cur.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO template (id, data) VALUES (1, ?)",
                    (json.dumps(DEFAULT_TEMPLATE),),
                )
            conn.commit()

    def load(self) -> List[Dict]:
        with self.db.connect() as conn:
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

    def save(self, template_data: List[Dict]) -> None:
        self._validate_template(template_data)
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE template SET data = ? WHERE id = 1",
                (json.dumps(template_data),),
            )
            conn.commit()

    @staticmethod
    def flatten(template_data: Sequence[Dict]) -> List[Dict]:
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
                        "importance": int(
                            sub.get("importance", item.get("importance", 1))
                        ),
                    }
                )
        return flat

    @staticmethod
    def _validate_template(template_data: Iterable[Dict]) -> None:
        if not isinstance(template_data, list):
            raise ValueError("Template must be a list")
        for item in template_data:
            if not isinstance(item, dict) or "id" not in item or "text" not in item:
                raise ValueError("Each item must have id and text")
            item.setdefault("importance", 1)
            item.setdefault("subitems", [])


class DayRepository:
    def __init__(self, db: Database, templates: TemplateRepository) -> None:
        self.db = db
        self.templates = templates

    def init_schema(self) -> None:
        with self.db.connect() as conn:
            cur = conn.cursor()
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
            conn.commit()

    def instantiate_day_if_needed(self, day: date) -> None:
        day_str = day.isoformat()
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM day_item WHERE day = ?", (day_str,)
            )
            if cur.fetchone()[0] > 0:
                return
            template_data = self.templates.load()
            flat = self.templates.flatten(template_data)
            for row in flat:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO day_item (
                        day, item_id, item_text, importance, checked, evidence, why, checked_at
                    )
                    VALUES (?, ?, ?, ?, 0, '', '', NULL)
                    """,
                    (day_str, row["item_id"], row["item_text"], row["importance"]),
                )
            conn.commit()

    def get_day_items(self, day: date) -> List[sqlite3.Row]:
        self.instantiate_day_if_needed(day)
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT * FROM day_item WHERE day = ? ORDER BY item_id",
                (day.isoformat(),),
            )
            return cur.fetchall()

    def set_item_checked(
        self, day: date, item_id: str, checked: bool, evidence: str, why: str
    ) -> None:
        if checked and not evidence.strip():
            raise ValueError("Evidence is required")
        if self.is_day_closed(day):
            raise ValueError("Day is closed. Reopen to edit.")
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE day_item
                SET checked = ?,
                    evidence = ?,
                    why = ?,
                    checked_at = CASE WHEN ? = 1 THEN ? ELSE NULL END
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

    def get_checked_days(self, month_start: date, month_end: date) -> set[str]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT day FROM day_item
                WHERE day BETWEEN ? AND ? AND checked = 1
                """,
                (month_start.isoformat(), month_end.isoformat()),
            )
            return {row[0] for row in cur.fetchall()}

    def is_day_closed(self, day: date) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(
                "SELECT closed FROM day_status WHERE day = ?", (day.isoformat(),)
            )
            row = cur.fetchone()
            return bool(row[0]) if row else False

    def set_day_closed(self, day: date, closed: bool) -> None:
        with self.db.connect() as conn:
            if closed:
                conn.execute(
                    """
                    INSERT INTO day_status (day, closed, closed_at)
                    VALUES (?, 1, ?)
                    ON CONFLICT(day) DO UPDATE SET closed = 1, closed_at = excluded.closed_at
                    """,
                    (day.isoformat(), datetime.now().isoformat(timespec="seconds")),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO day_status (day, closed, closed_at)
                    VALUES (?, 0, NULL)
                    ON CONFLICT(day) DO UPDATE SET closed = 0, closed_at = NULL
                    """,
                    (day.isoformat(),),
                )
            conn.commit()


@dataclass
class DayState:
    items: List[sqlite3.Row]
    closed: bool


class QuotaService:
    def __init__(self, day_repo: DayRepository, template_repo: TemplateRepository) -> None:
        self.day_repo = day_repo
        self.template_repo = template_repo

    def initialize(self) -> None:
        self.template_repo.init_schema()
        self.template_repo.ensure_default()
        self.day_repo.init_schema()

    def get_day(self, day: date) -> DayState:
        items = self.day_repo.get_day_items(day)
        closed = self.day_repo.is_day_closed(day)
        return DayState(items=items, closed=closed)

    def mark_item(
        self, day: date, item_id: str, checked: bool, evidence: str, why: str
    ) -> None:
        self.day_repo.set_item_checked(day, item_id, checked, evidence, why)

    def close_day(self, day: date) -> None:
        self.day_repo.set_day_closed(day, True)

    def reopen_day(self, day: date) -> None:
        self.day_repo.set_day_closed(day, False)

    def get_checked_days(self, month_start: date, month_end: date) -> set[str]:
        return self.day_repo.get_checked_days(month_start, month_end)

    def load_template(self) -> List[Dict]:
        return self.template_repo.load()

    def save_template(self, template_data: List[Dict]) -> None:
        self.template_repo.save(template_data)

    def reset_template(self) -> List[Dict]:
        self.template_repo.save(json.loads(json.dumps(DEFAULT_TEMPLATE)))
        return DEFAULT_TEMPLATE.copy()
