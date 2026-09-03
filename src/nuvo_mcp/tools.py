"""Инструменты, которые видит агент.

Инструменты — обычные функции: их можно вызвать и проверить без транспорта MCP,
а сервер лишь регистрирует их. Отбор и разбор снимка живут отдельными чистыми
функциями, поэтому проверяются без сети.

Умные списки («Запланировано», «В любое время», «Журнал») здесь не
повторяются: их правила живут во фронтенде, и копия на Python неизбежно бы с
ними разошлась. Исключение одно — «Сегодня»: без него агент не может ответить
на главный вопрос дня. Правило переписано с `frontend/src/domain/lists.ts`
(`isInToday`) дословно и закреплено тестом.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from nuvo_mcp.api import NuvoApi, NuvoError

#: Значения поля «когда», у которых нет своей даты. Пятое — `scheduled` — как
#: раз и означает «есть дата», поэтому словом его не задают.
WHEN_WORDS = ("today", "evening", "anytime", "someday")


# ─── разбор снимка ────────────────────────────────────────────────────────────


def as_date(value: str, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise NuvoError(f"{what} пишется как ГГГГ-ММ-ДД, а не «{value}»") from None


def brief(task: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Дело в том виде, в каком его показывают в списке."""

    return {
        "id": task["id"],
        "title": task["title"],
        "when": task["when_kind"],
        "when_date": task["when_date"],
        "deadline": task["deadline"],
        "project": title_of(state["projects"], task["project_id"]),
        "area": title_of(state["areas"], task["area_id"]),
        "tags": [item["title"] for item in task["tags"]],
        "done": task["completed_at"] is not None,
    }


def title_of(rows: list[dict[str, Any]], row_id: int | None) -> str | None:
    if row_id is None:
        return None
    return next((row["title"] for row in rows if row["id"] == row_id), None)


def find_by_title(rows: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    """Поиск по названию без оглядки на регистр: человек пишет как говорит.

    Выброшенное в корзину не в счёт: положить новое дело в удалённый проект —
    значит спрятать его там, где человек уже не смотрит.
    """

    return next(
        (
            row
            for row in rows
            if row["title"].lower() == title.lower() and not row.get("trashed_at")
        ),
        None,
    )


def is_active(task: dict[str, Any]) -> bool:
    """Дело живо: не в корзине и не убрано в журнал."""

    return task["trashed_at"] is None and task["logged_at"] is None


def is_finished(task: dict[str, Any]) -> bool:
    return task["completed_at"] is not None or task["canceled_at"] is not None


def started_by(task: dict[str, Any], today: date) -> bool:
    """Дело уже началось. Списано с `startedBy` во фронтенде."""

    if task["when_kind"] in ("today", "evening"):
        return True
    if task["when_kind"] != "scheduled" or task["when_date"] is None:
        return False
    return date.fromisoformat(task["when_date"]) <= today


def tasks_of(state: dict[str, Any], **filters: Any) -> list[dict[str, Any]]:
    """Отбор по полям дела. Правила умных списков здесь не повторяются."""

    when = filters.get("when")
    project = filters.get("project")
    tag = filters.get("tag")
    include_done = filters.get("include_done", False)

    found = find_by_title(state["projects"], project) if project else None
    project_id = found["id"] if found else None

    chosen: list[dict[str, Any]] = []
    for task in state["tasks"]:
        if task["trashed_at"]:
            continue
        if not include_done and (task["completed_at"] or task["logged_at"]):
            continue
        if when and task["when_kind"] != when:
            continue
        if project and task["project_id"] != project_id:
            continue
        if tag and not any(item["title"].lower() == tag.lower() for item in task["tags"]):
            continue
        chosen.append(brief(task, state))
    return chosen


def day_view(state: dict[str, Any], today: date) -> dict[str, Any]:
    """Что стоит на сегодня и что просрочено.

    Завершённые не показываются: в приложении они дочёркиваются и остаются на
    глазах до уборки в журнал, а агенту нужен список того, что ещё делать.
    """

    planned: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    for task in state["tasks"]:
        if not is_active(task) or is_finished(task):
            continue
        if started_by(task, today):
            planned.append(brief(task, state))
        if task["deadline"] and date.fromisoformat(task["deadline"]) < today:
            overdue.append(brief(task, state))
    return {"date": today.isoformat(), "today": planned, "overdue": overdue}


def matches(task: dict[str, Any], query: str) -> bool:
    needle = query.lower()
    return needle in task["title"].lower() or needle in task["notes"].lower()


def with_date(notes: str, text: str, today: date) -> str:
    """Дописать абзац с датой, не тронув написанное раньше."""

    paragraph = f"**{today.isoformat()}** — {text.strip()}"
    body = notes.rstrip()
    return f"{body}\n\n{paragraph}" if body else paragraph


def checklist_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    """Чек-лист в том виде, в каком его принимает PATCH: только название и
    отметка. Правка присылает список целиком — иначе не выйдет ни переставить
    пункт, ни удалить его."""

    return [
        {"title": item["title"], "completed": item["completed_at"] is not None}
        for item in task["checklist"]
    ]


# ─── инструменты ──────────────────────────────────────────────────────────────


def make_tools(api: NuvoApi) -> dict[str, Any]:
    def task_by_id(state: dict[str, Any], task_id: int) -> dict[str, Any]:
        found = next((task for task in state["tasks"] if task["id"] == task_id), None)
        if found is None:
            raise NuvoError(f"Дела №{task_id} нет. Найдите его через search_tasks или list_tasks.")
        return found

    def project_id_by_title(state: dict[str, Any], title: str) -> int:
        found = find_by_title(state["projects"], title)
        if found is None:
            names = ", ".join(f"«{p['title']}»" for p in state["projects"] if not p["trashed_at"])
            raise NuvoError(
                f"Проекта «{title}» нет. Есть: {names or 'ни одного'}. "
                "Новый заводится инструментом create_project."
            )
        return found["id"]

    def area_id_by_title(state: dict[str, Any], title: str) -> int:
        found = find_by_title(state["areas"], title)
        if found is None:
            names = ", ".join(f"«{a['title']}»" for a in state["areas"] if not a["trashed_at"])
            raise NuvoError(
                f"Области «{title}» нет. Есть: {names or 'ни одной'}. "
                "Новая заводится инструментом create_area."
            )
        return found["id"]

    def patch(task_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return api.call("PATCH", f"/api/tasks/{task_id}", json=body)

    def when_fields(when: str) -> dict[str, Any]:
        if when in WHEN_WORDS:
            return {"when_kind": when}
        return {"when_kind": "scheduled", "when_date": as_date(when, "Дата дела").isoformat()}

    # ─── чтение ───────────────────────────────────────────────────────────────

    def list_lists() -> dict[str, Any]:
        state = api.state()
        return {
            "projects": [p["title"] for p in state["projects"] if not p["trashed_at"]],
            "areas": [a["title"] for a in state["areas"] if not a["trashed_at"]],
            "saved_filters": [f["title"] for f in state.get("smart_lists", [])],
            "tags": [t["title"] for t in state["tags"]],
        }

    def list_tasks(
        when: str | None = None,
        project: str | None = None,
        tag: str | None = None,
        include_done: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        found = tasks_of(
            api.state(), when=when, project=project, tag=tag, include_done=include_done
        )
        return found[: max(1, limit)]

    def today() -> dict[str, Any]:
        return day_view(api.state(), date.today())

    def search_tasks(
        query: str, include_done: bool = False, limit: int = 20
    ) -> list[dict[str, Any]]:
        if not query.strip():
            raise NuvoError("Искать нечего: запрос пустой.")
        state = api.state()
        found = [
            brief(task, state)
            for task in state["tasks"]
            if task["trashed_at"] is None
            and (include_done or not is_finished(task))
            and matches(task, query)
        ]
        return found[: max(1, limit)]

    def get_task(task_id: int) -> dict[str, Any]:
        state = api.state()
        task = task_by_id(state, task_id)
        return {
            **brief(task, state),
            "notes": task["notes"],
            "checklist": [
                {"title": item["title"], "done": item["completed_at"] is not None}
                for item in task["checklist"]
            ],
            "logged": task["logged_at"] is not None,
            "trashed": task["trashed_at"] is not None,
            "canceled": task["canceled_at"] is not None,
        }

    # ─── создание и правка ────────────────────────────────────────────────────

    def create_task(
        title: str,
        notes: str = "",
        when: str = "anytime",
        deadline: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "notes": notes}
        if deadline:
            body["deadline"] = as_date(deadline, "Срок").isoformat()
        body.update(when_fields(when))
        if project:
            body["project_id"] = project_id_by_title(api.state(), project)
        return api.call("POST", "/api/tasks", json=body)

    def update_task(
        task_id: int,
        title: str | None = None,
        notes: str | None = None,
        deadline: str | None = None,
        clear_deadline: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            key: value
            for key, value in {"title": title, "notes": notes}.items()
            if value is not None
        }
        if deadline:
            body["deadline"] = as_date(deadline, "Срок").isoformat()
        # Пустая строка сроком не бывает, поэтому снятие просят словом: иначе
        # «убрать срок» было бы неотличимо от «поле не трогать».
        if clear_deadline:
            body["clear_deadline"] = True
        if not body:
            raise NuvoError("Нечего менять: не задано ни одно поле.")
        return patch(task_id, body)

    def add_note(task_id: int, text: str) -> dict[str, Any]:
        if not text.strip():
            raise NuvoError("Пустую заметку дописывать незачем.")
        state = api.state()
        task = task_by_id(state, task_id)
        return patch(task_id, {"notes": with_date(task["notes"], text, date.today())})

    def move_task(
        task_id: int, project: str | None = None, area: str | None = None
    ) -> dict[str, Any]:
        """Перенос дела. Без обоих названий дело уходит во «Входящие»."""

        if project and area:
            raise NuvoError("Дело живёт либо в проекте, либо в области — выберите одно.")
        state = api.state()
        if project:
            return patch(task_id, {"project_id": project_id_by_title(state, project)})
        if area:
            # Проект снимается заодно: иначе дело осталось бы в нём, а область
            # оказалась бы записана в поле, которого никто не увидит.
            return patch(task_id, {"area_id": area_id_by_title(state, area), "clear_project": True})
        return patch(task_id, {"clear_project": True, "clear_area": True})

    # ─── состояние дела ───────────────────────────────────────────────────────

    def schedule_task(task_id: int, when: str) -> dict[str, Any]:
        return patch(task_id, when_fields(when))

    def complete_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"completed": True})

    def reopen_task(task_id: int) -> dict[str, Any]:
        # Снимаем и завершение, и отмену: вернуть в работу можно из обоих.
        return patch(task_id, {"completed": False, "canceled": False})

    def log_task(task_id: int) -> dict[str, Any]:
        task = task_by_id(api.state(), task_id)
        if not is_finished(task):
            raise NuvoError(
                f"«{task['title']}» ещё не завершено. Журнал — место закрытых дел: "
                "сначала complete_task, иначе дело просто пропадёт с глаз."
            )
        return patch(task_id, {"logged": True})

    def trash_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"trashed": True})

    def restore_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"trashed": False})

    # ─── чек-лист ─────────────────────────────────────────────────────────────

    def add_checklist_item(task_id: int, title: str) -> dict[str, Any]:
        task = task_by_id(api.state(), task_id)
        items = checklist_of(task)
        items.append({"title": title, "completed": False})
        return patch(task_id, {"checklist": items})

    def check_checklist_item(task_id: int, title: str, done: bool = True) -> dict[str, Any]:
        task = task_by_id(api.state(), task_id)
        items = checklist_of(task)
        hits = [item for item in items if item["title"].lower() == title.lower()]
        if not hits:
            hits = [item for item in items if title.lower() in item["title"].lower()]
        if not hits:
            names = ", ".join(f"«{item['title']}»" for item in items)
            raise NuvoError(f"Пункта «{title}» в чек-листе нет. Есть: {names or 'ни одного'}.")
        if len(hits) > 1:
            names = ", ".join(f"«{item['title']}»" for item in hits)
            raise NuvoError(f"«{title}» подходит сразу нескольким пунктам: {names}.")
        hits[0]["completed"] = done
        return patch(task_id, {"checklist": items})

    # ─── теги ─────────────────────────────────────────────────────────────────

    def tag_task(task_id: int, tag: str) -> dict[str, Any]:
        state = api.state()
        task = task_by_id(state, task_id)
        found = find_by_title(state["tags"], tag)
        # Тега может не быть — заводим. Запрос идемпотентен: сервер вернёт
        # существующий, если он всё же был.
        row = found or api.call("POST", "/api/tags", json={"title": tag})
        ids = {item["id"] for item in task["tags"]} | {row["id"]}
        return patch(task_id, {"tag_ids": sorted(ids)})

    def untag_task(task_id: int, tag: str) -> dict[str, Any]:
        state = api.state()
        task = task_by_id(state, task_id)
        ids = [item["id"] for item in task["tags"] if item["title"].lower() != tag.lower()]
        if len(ids) == len(task["tags"]):
            raise NuvoError(f"На деле «{task['title']}» тега «{tag}» и не было.")
        return patch(task_id, {"tag_ids": ids})

    # ─── проекты и области ────────────────────────────────────────────────────

    def create_project(title: str, area: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if area:
            body["area_id"] = area_id_by_title(api.state(), area)
        return api.call("POST", "/api/projects", json=body)

    def create_area(title: str) -> dict[str, Any]:
        return api.call("POST", "/api/areas", json={"title": title})

    return {
        "list_lists": list_lists,
        "list_tasks": list_tasks,
        "today": today,
        "search_tasks": search_tasks,
        "get_task": get_task,
        "create_task": create_task,
        "update_task": update_task,
        "add_note": add_note,
        "move_task": move_task,
        "schedule_task": schedule_task,
        "complete_task": complete_task,
        "reopen_task": reopen_task,
        "log_task": log_task,
        "trash_task": trash_task,
        "restore_task": restore_task,
        "add_checklist_item": add_checklist_item,
        "check_checklist_item": check_checklist_item,
        "tag_task": tag_task,
        "untag_task": untag_task,
        "create_project": create_project,
        "create_area": create_area,
    }


#: Описания читает модель, поэтому в них сказано не «что делает функция», а
#: «когда её звать»: по одному только имени `log_task` выбор не сделать.
DESCRIPTIONS = {
    "list_lists": (
        "Что вообще есть у человека: проекты, области, теги и сохранённые отборы — "
        "одними названиями. Зовите первым, если не знаете, куда класть дело и какие "
        "теги существуют."
    ),
    "list_tasks": (
        "Дела с отбором по полю «когда» (today, evening, anytime, someday, scheduled), "
        "проекту или тегу. Без отбора — все незакрытые дела. Завершённые показываются "
        "только по просьбе (include_done)."
    ),
    "today": (
        "Главный вопрос дня одним вызовом: что стоит на сегодня и что просрочено по сроку. "
        "Зовите, когда спрашивают «что у меня сегодня», «что горит», «с чего начать». "
        "Завершённые сюда не попадают."
    ),
    "search_tasks": (
        "Поиск дела по словам из названия или заметки. Зовите перед тем, как создать дело: "
        "так не появится второй «Позвонить врачу» рядом с первым."
    ),
    "get_task": (
        "Одно дело целиком: заметка, чек-лист, теги, проект, сроки и состояние. "
        "Зовите перед правкой заметки или чек-листа — чтобы знать, что там уже написано."
    ),
    "create_task": (
        "Завести новое дело. `when`: today — «Сегодня», evening — «Вечером», anytime — "
        "«В любое время» (по умолчанию), someday — «Когда-нибудь», либо дата ГГГГ-ММ-ДД. "
        "`deadline` — крайний срок, он не то же самое, что день выполнения. "
        "Сначала поищите search_tasks: дубликат хуже, чем ничего."
    ),
    "update_task": (
        "Переписать название, заметку целиком или срок; `clear_deadline=true` снимает срок "
        "совсем. Заметку почти всегда нужно не переписывать, а дописывать — для этого есть "
        "add_note. День и «когда» меняет schedule_task."
    ),
    "add_note": (
        "Дописать к заметке дела абзац с сегодняшней датой, не тронув написанное раньше. "
        "Это здешняя замена комментариям: чем кончился разговор, что выяснилось, что решили."
    ),
    "move_task": (
        "Перенести дело в проект или в область. Без указания того и другого дело уходит "
        "во «Входящие». Новый проект заводится через create_project."
    ),
    "schedule_task": (
        "Назначить, когда делом заниматься: today — «Сегодня», evening — «Вечером», "
        "anytime — «В любое время», someday — «Когда-нибудь» (отложить), либо дата "
        "ГГГГ-ММ-ДД. «Сегодня» ставьте только тому, за что человек действительно берётся "
        "сегодня: переполненный день перестают читать."
    ),
    "complete_task": "Отметить дело сделанным. Повторяющееся при этом само родит следующее.",
    "reopen_task": (
        "Вернуть дело в работу: снимает и отметку «сделано», и отмену, и уборку в журнал. "
        "Зовите, если завершили по ошибке или дело вернулось."
    ),
    "log_task": (
        "Убрать завершённое дело в журнал, чтобы оно ушло из списков. Незавершённое "
        "убрать нельзя — сначала complete_task."
    ),
    "trash_task": (
        "Выбросить дело в корзину. Обратимо: restore_task вернёт. Окончательного "
        "удаления у агента нет намеренно — корзину человек чистит сам."
    ),
    "restore_task": "Достать дело из корзины обратно в работу.",
    "add_checklist_item": (
        "Добавить пункт в чек-лист дела — маленький шаг внутри одного дела. "
        "Если шагов больше десятка или у них свои сроки, это не чек-лист, а проект."
    ),
    "check_checklist_item": (
        "Отметить пункт чек-листа выполненным (или снять отметку, done=false). "
        "Пункт ищется по названию, хватит и части — лишь бы она была одна такая."
    ),
    "tag_task": (
        "Повесить тег на дело. Если такого тега ещё нет, он заводится. Прежние теги "
        "дела остаются на месте."
    ),
    "untag_task": "Снять тег с дела. Остальные теги остаются.",
    "create_project": (
        "Завести проект — дело из нескольких шагов со своим списком. Можно сразу положить "
        "в область. Сперва посмотрите list_lists: проект с таким названием может уже быть."
    ),
    "create_area": (
        "Завести область — постоянную часть жизни или работы («Дом», «Здоровье»), в которой "
        "живут проекты и дела. Областей заводят единицы; чаще нужен проект."
    ),
}
