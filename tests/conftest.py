"""Подложный сервер вместо настоящего.

Пакет не зависит от бэкенда, поэтому и его тесты не поднимают ни FastAPI, ни
базу: HTTP подменяется транспортом httpx. Здесь проверяется, что инструмент
шлёт — какой метод, куда и с каким телом. Что на это ответит настоящее API,
проверяют тесты бэкенда (`backend/tests/test_mcp.py`).
"""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from nuvo_mcp.api import NuvoApi

TASK_FIELDS: dict[str, Any] = {
    "id": 1,
    "title": "Дело",
    "notes": "",
    "area_id": None,
    "project_id": None,
    "heading_id": None,
    "position": 0,
    "when_kind": "anytime",
    "when_date": None,
    "deadline": None,
    "start_minutes": None,
    "duration_minutes": None,
    "remind_at": None,
    "reminded_at": None,
    "created_at": "2026-09-01T10:00:00Z",
    "completed_at": None,
    "canceled_at": None,
    "logged_at": None,
    "trashed_at": None,
    "checklist": [],
    "tags": [],
    "repeat_unit": None,
    "repeat_interval": 1,
    "repeat_weekdays": None,
    "repeat_mode": "after",
}


def task(**changed: Any) -> dict[str, Any]:
    """Дело со всеми полями снимка: инструменты читают их без оглядки."""

    return TASK_FIELDS | changed


def item(title: str, completed: bool = False) -> dict[str, Any]:
    return {
        "id": abs(hash(title)) % 10_000,
        "title": title,
        "position": 0,
        "completed_at": "2026-09-01T10:00:00Z" if completed else None,
    }


def snapshot(**parts: Any) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "areas": [],
        "projects": [],
        "headings": [],
        "tasks": [],
        "tags": [],
        "smart_lists": [],
    }
    return empty | parts


@dataclass
class Sent:
    method: str
    path: str
    body: Any


@dataclass
class Fake:
    """Записывает отправленное и отдаёт заранее оговорённый снимок."""

    state: dict[str, Any]
    api: NuvoApi = field(init=False)
    sent: list[Sent] = field(default_factory=list)

    def __post_init__(self) -> None:
        transport = httpx.MockTransport(self.handle)
        client = httpx.Client(transport=transport, base_url="http://nuvo.test")
        self.api = NuvoApi("http://nuvo.test", "nv_test", client=client)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        if request.method == "GET" and path == "/api/state":
            return httpx.Response(200, json=self.state)
        self.sent.append(Sent(request.method, path, body))
        if path == "/api/tags":
            return httpx.Response(201, json={"id": 77, "title": body["title"], "position": 0})
        return httpx.Response(200, json={"ok": True})

    @property
    def last(self) -> Sent:
        return self.sent[-1]


@pytest.fixture
def fake():
    def build(**parts: Any) -> Fake:
        return Fake(snapshot(**parts))

    return build
