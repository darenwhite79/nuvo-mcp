"""Инструменты: что именно уходит в API и как разбирается снимок."""

from datetime import date

import pytest
from conftest import item, snapshot, task

from nuvo_mcp.api import NuvoError
from nuvo_mcp.tools import day_view, make_tools, tasks_of, with_date

СЕГОДНЯ = date(2026, 9, 3)


# ─── разбор снимка ────────────────────────────────────────────────────────────


def test_сегодня_собирает_начавшиеся_и_просроченные():
    state = snapshot(
        tasks=[
            task(id=1, title="Помечено сегодня", when_kind="today"),
            task(id=2, title="Вечером", when_kind="evening"),
            task(id=3, title="День настал", when_kind="scheduled", when_date="2026-09-01"),
            task(id=4, title="День ещё не настал", when_kind="scheduled", when_date="2026-09-10"),
            task(id=5, title="Когда-нибудь", when_kind="someday"),
            task(id=6, title="Срок прошёл", deadline="2026-08-30"),
        ]
    )

    view = day_view(state, СЕГОДНЯ)

    assert [t["title"] for t in view["today"]] == ["Помечено сегодня", "Вечером", "День настал"]
    assert [t["title"] for t in view["overdue"]] == ["Срок прошёл"]
    assert view["date"] == "2026-09-03"


def test_сегодня_молчит_о_закрытом_и_выброшенном():
    state = snapshot(
        tasks=[
            task(id=1, title="Сделано", when_kind="today", completed_at="2026-09-03T09:00:00Z"),
            task(id=2, title="В корзине", when_kind="today", trashed_at="2026-09-03T09:00:00Z"),
            task(id=3, title="В журнале", when_kind="today", logged_at="2026-09-03T09:00:00Z"),
            task(id=4, title="Осталось", when_kind="today"),
        ]
    )

    assert [t["title"] for t in day_view(state, СЕГОДНЯ)["today"]] == ["Осталось"]


def test_отбор_по_проекту_и_тегу_не_смотрит_на_регистр():
    state = snapshot(
        projects=[{"id": 5, "title": "Ремонт", "trashed_at": None}],
        tasks=[
            task(id=1, title="Купить краску", project_id=5, tags=[{"id": 9, "title": "дом"}]),
            task(id=2, title="Постороннее"),
        ],
    )

    assert [t["title"] for t in tasks_of(state, project="рЕмОнТ")] == ["Купить краску"]
    assert [t["title"] for t in tasks_of(state, tag="ДОМ")] == ["Купить краску"]
    assert tasks_of(state)[0]["project"] == "Ремонт"


def test_заметка_дописывается_с_датой_и_не_затирает_прежнее():
    было = "Первый разговор"

    стало = with_date(было, "Перезвонить в четверг", СЕГОДНЯ)

    assert стало == "Первый разговор\n\n**2026-09-03** — Перезвонить в четверг"
    assert with_date("", "Начало", СЕГОДНЯ) == "**2026-09-03** — Начало"


# ─── что уходит в API ─────────────────────────────────────────────────────────


def test_дата_вместо_слова_ставит_запланировано(fake):
    stand = fake(tasks=[task(id=1)])

    make_tools(stand.api)["schedule_task"](task_id=1, when="2026-12-31")

    assert stand.last.body == {"when_kind": "scheduled", "when_date": "2026-12-31"}


def test_слово_когда_нибудь_уходит_как_есть(fake):
    stand = fake(tasks=[task(id=1)])

    make_tools(stand.api)["schedule_task"](task_id=1, when="someday")

    assert stand.last.body == {"when_kind": "someday"}


def test_кривая_дата_объясняет_формат(fake):
    tools = make_tools(fake(tasks=[task(id=1)]).api)

    with pytest.raises(NuvoError) as error:
        tools["schedule_task"](task_id=1, when="31.12.2026")

    assert "ГГГГ-ММ-ДД" in str(error.value)


def test_add_note_шлёт_заметку_целиком(fake):
    stand = fake(tasks=[task(id=1, notes="Старое")])

    make_tools(stand.api)["add_note"](task_id=1, text="Новое")

    assert stand.last.path == "/api/tasks/1"
    assert stand.last.body["notes"].startswith("Старое\n\n**")
    assert stand.last.body["notes"].endswith("— Новое")


def test_пункт_чек_листа_добавляется_к_прежним(fake):
    stand = fake(tasks=[task(id=1, checklist=[item("Первый", completed=True)])])

    make_tools(stand.api)["add_checklist_item"](task_id=1, title="Второй")

    assert stand.last.body["checklist"] == [
        {"title": "Первый", "completed": True},
        {"title": "Второй", "completed": False},
    ]


def test_пункт_ищется_по_части_названия(fake):
    stand = fake(tasks=[task(id=1, checklist=[item("Позвонить в банк"), item("Забрать справку")])])

    make_tools(stand.api)["check_checklist_item"](task_id=1, title="банк")

    assert stand.last.body["checklist"] == [
        {"title": "Позвонить в банк", "completed": True},
        {"title": "Забрать справку", "completed": False},
    ]


def test_неоднозначный_пункт_не_отмечается_наугад(fake):
    tools = make_tools(fake(tasks=[task(id=1, checklist=[item("Звонок А"), item("Звонок Б")])]).api)

    with pytest.raises(NuvoError) as error:
        tools["check_checklist_item"](task_id=1, title="Звонок")

    assert "нескольким" in str(error.value)


def test_новый_тег_не_сбивает_прежние(fake):
    stand = fake(tasks=[task(id=1, tags=[{"id": 3, "title": "дом"}])], tags=[])

    make_tools(stand.api)["tag_task"](task_id=1, tag="срочно")

    assert stand.sent[0].path == "/api/tags"
    assert stand.last.body == {"tag_ids": [3, 77]}


def test_известный_тег_не_заводится_заново(fake):
    stand = fake(tasks=[task(id=1)], tags=[{"id": 3, "title": "Дом", "position": 0}])

    make_tools(stand.api)["tag_task"](task_id=1, tag="дом")

    assert [sent.path for sent in stand.sent] == ["/api/tasks/1"]
    assert stand.last.body == {"tag_ids": [3]}


def test_журнал_не_принимает_незавершённое(fake):
    tools = make_tools(fake(tasks=[task(id=1, title="Ещё в работе")]).api)

    with pytest.raises(NuvoError) as error:
        tools["log_task"](task_id=1)

    assert "complete_task" in str(error.value)


def test_завершённое_в_журнал_уходит(fake):
    stand = fake(tasks=[task(id=1, completed_at="2026-09-03T09:00:00Z")])

    make_tools(stand.api)["log_task"](task_id=1)

    assert stand.last.body == {"logged": True}


def test_перенос_в_область_убирает_дело_из_проекта(fake):
    stand = fake(
        areas=[{"id": 4, "title": "Дом", "trashed_at": None}],
        tasks=[task(id=1, project_id=2)],
    )

    make_tools(stand.api)["move_task"](task_id=1, area="Дом")

    assert stand.last.body == {"area_id": 4, "clear_project": True}


def test_перенос_без_места_возвращает_во_входящие(fake):
    stand = fake(tasks=[task(id=1, project_id=2)])

    make_tools(stand.api)["move_task"](task_id=1)

    assert stand.last.body == {"clear_project": True, "clear_area": True}


def test_несуществующий_проект_называет_имеющиеся(fake):
    tools = make_tools(fake(projects=[{"id": 5, "title": "Ремонт", "trashed_at": None}]).api)

    with pytest.raises(NuvoError) as error:
        tools["create_task"](title="Дело", project="Ремот")

    assert "«Ремонт»" in str(error.value)


def test_поиск_смотрит_и_в_заметку(fake):
    stand = fake(
        tasks=[
            task(id=1, title="Позвонить", notes="по поводу договора"),
            task(id=2, title="Договориться о встрече"),
            task(id=3, title="Постороннее"),
        ]
    )

    found = make_tools(stand.api)["search_tasks"](query="догово")

    assert [t["id"] for t in found] == [1, 2]


def test_снятие_отсутствующего_тега_говорит_прямо(fake):
    tools = make_tools(fake(tasks=[task(id=1, title="Дело")]).api)

    with pytest.raises(NuvoError) as error:
        tools["untag_task"](task_id=1, tag="дом")

    assert "и не было" in str(error.value)


def test_у_каждого_инструмента_есть_описание(fake):
    from nuvo_mcp.tools import DESCRIPTIONS

    assert set(make_tools(fake().api)) == set(DESCRIPTIONS)


def test_выброшенный_проект_не_принимает_новые_дела(fake):
    tools = make_tools(
        fake(
            projects=[
                {"id": 5, "title": "Ремонт", "trashed_at": "2026-09-01T10:00:00Z"},
                {"id": 6, "title": "Отпуск", "trashed_at": None},
            ]
        ).api
    )

    with pytest.raises(NuvoError) as error:
        tools["create_task"](title="Купить краску", project="Ремонт")

    # Название названо как отсутствующее, а в списке живых его уже нет.
    assert str(error.value).startswith("Проекта «Ремонт» нет.")
    assert "Есть: «Отпуск»." in str(error.value)
