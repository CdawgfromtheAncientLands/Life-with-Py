from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from core import Database, DayRepository, QuotaService, TemplateRepository


def make_service(tmp_path: Path) -> QuotaService:
    database = Database(tmp_path / "quota.db")
    template_repo = TemplateRepository(database)
    day_repo = DayRepository(database, template_repo)
    service = QuotaService(day_repo, template_repo)
    service.initialize()
    return service


def test_initialize_creates_default_items(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    today = date.today()

    state = service.get_day(today)

    assert state.items
    assert all("item_id" in row.keys() for row in state.items)


def test_mark_item_requires_evidence_when_checked(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    today = date.today()
    item_id = service.get_day(today).items[0]["item_id"]

    with pytest.raises(ValueError):
        service.mark_item(today, item_id, True, "   ", "")


def test_cannot_mark_closed_day(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    today = date.today()
    item_id = service.get_day(today).items[0]["item_id"]

    service.close_day(today)

    with pytest.raises(ValueError):
        service.mark_item(today, item_id, True, "evidence", "")

    service.reopen_day(today)
    service.mark_item(today, item_id, True, "did it", "because")

    state = service.get_day(today)
    assert any(row["item_id"] == item_id and row["checked"] for row in state.items)
