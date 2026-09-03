"""The tools an agent sees.

Tools are plain functions: they can be called and checked without the MCP
transport, and the server only registers them. Filtering and snapshot parsing
live in separate pure functions, so they are tested without a network.

The smart lists ("Upcoming", "Anytime", "Logbook") are not reimplemented here:
their rules live in the frontend, and a Python copy would inevitably drift away
from them. There is one exception — "Today": without it the agent cannot answer
the main question of the day. That rule is transcribed word for word from
`frontend/src/domain/lists.ts` (`isInToday`) and pinned by a test.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from nuvo_mcp.api import NuvoApi, NuvoError

#: Values of the "when" field that carry no date of their own. The fifth one —
#: `scheduled` — means exactly "has a date", which is why it is never spelled out.
WHEN_WORDS = ("today", "evening", "anytime", "someday")


# ─── parsing the snapshot ─────────────────────────────────────────────────────


def as_date(value: str, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise NuvoError(f"{what} is written as YYYY-MM-DD, not '{value}'") from None


def brief(task: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """A task the way it is shown in a list."""

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
    """Look up by title regardless of case: people write the way they speak.

    Anything in the trash does not count: putting a new task into a deleted
    project means hiding it where nobody looks any more.
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
    """The task is alive: not in the trash and not filed away in the logbook."""

    return task["trashed_at"] is None and task["logged_at"] is None


def is_finished(task: dict[str, Any]) -> bool:
    return task["completed_at"] is not None or task["canceled_at"] is not None


def started_by(task: dict[str, Any], today: date) -> bool:
    """The task has already started. Copied from `startedBy` in the frontend."""

    if task["when_kind"] in ("today", "evening"):
        return True
    if task["when_kind"] != "scheduled" or task["when_date"] is None:
        return False
    return date.fromisoformat(task["when_date"]) <= today


def tasks_of(state: dict[str, Any], **filters: Any) -> list[dict[str, Any]]:
    """Filter by task fields. Smart-list rules are not reimplemented here."""

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
    """What is on for today and what is overdue.

    Finished tasks are left out: in the app they are struck through and stay in
    sight until they are filed away, but the agent needs the list of what is
    still to be done.
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
    """Append a dated paragraph without touching what was written earlier."""

    paragraph = f"**{today.isoformat()}** — {text.strip()}"
    body = notes.rstrip()
    return f"{body}\n\n{paragraph}" if body else paragraph


def checklist_of(task: dict[str, Any]) -> list[dict[str, Any]]:
    """The checklist in the shape PATCH accepts: title and tick only. An edit
    sends the whole list — otherwise there would be no way to reorder an item
    or to delete one."""

    return [
        {"title": item["title"], "completed": item["completed_at"] is not None}
        for item in task["checklist"]
    ]


# ─── tools ────────────────────────────────────────────────────────────────────


def make_tools(api: NuvoApi) -> dict[str, Any]:
    def task_by_id(state: dict[str, Any], task_id: int) -> dict[str, Any]:
        found = next((task for task in state["tasks"] if task["id"] == task_id), None)
        if found is None:
            raise NuvoError(
                f"There is no task #{task_id}. Find it with search_tasks or list_tasks."
            )
        return found

    def project_id_by_title(state: dict[str, Any], title: str) -> int:
        found = find_by_title(state["projects"], title)
        if found is None:
            names = ", ".join(f"'{p['title']}'" for p in state["projects"] if not p["trashed_at"])
            raise NuvoError(
                f"There is no project '{title}'. There is: {names or 'none at all'}. "
                "A new one is created with create_project."
            )
        return found["id"]

    def area_id_by_title(state: dict[str, Any], title: str) -> int:
        found = find_by_title(state["areas"], title)
        if found is None:
            names = ", ".join(f"'{a['title']}'" for a in state["areas"] if not a["trashed_at"])
            raise NuvoError(
                f"There is no area '{title}'. There is: {names or 'none at all'}. "
                "A new one is created with create_area."
            )
        return found["id"]

    def patch(task_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return api.call("PATCH", f"/api/tasks/{task_id}", json=body)

    def when_fields(when: str) -> dict[str, Any]:
        if when in WHEN_WORDS:
            return {"when_kind": when}
        return {"when_kind": "scheduled", "when_date": as_date(when, "A task date").isoformat()}

    # ─── reading ──────────────────────────────────────────────────────────────

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
            raise NuvoError("Nothing to search for: the query is empty.")
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

    # ─── creating and editing ─────────────────────────────────────────────────

    def create_task(
        title: str,
        notes: str = "",
        when: str = "anytime",
        deadline: str | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "notes": notes}
        if deadline:
            body["deadline"] = as_date(deadline, "A deadline").isoformat()
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
            body["deadline"] = as_date(deadline, "A deadline").isoformat()
        # An empty string is never a deadline, so removing one is asked for by
        # name: otherwise "clear the deadline" would be indistinguishable from
        # "leave that field alone".
        if clear_deadline:
            body["clear_deadline"] = True
        if not body:
            raise NuvoError("Nothing to change: not a single field was given.")
        return patch(task_id, body)

    def add_note(task_id: int, text: str) -> dict[str, Any]:
        if not text.strip():
            raise NuvoError("There is no point appending an empty note.")
        state = api.state()
        task = task_by_id(state, task_id)
        return patch(task_id, {"notes": with_date(task["notes"], text, date.today())})

    def move_task(
        task_id: int, project: str | None = None, area: str | None = None
    ) -> dict[str, Any]:
        """Move a task. With neither name given, the task goes to the Inbox."""

        if project and area:
            raise NuvoError("A task lives either in a project or in an area — pick one.")
        state = api.state()
        if project:
            return patch(task_id, {"project_id": project_id_by_title(state, project)})
        if area:
            # The project is cleared along with it: otherwise the task would
            # stay inside it, and the area would be recorded in a field nobody
            # ever sees.
            return patch(task_id, {"area_id": area_id_by_title(state, area), "clear_project": True})
        return patch(task_id, {"clear_project": True, "clear_area": True})

    # ─── the state of a task ──────────────────────────────────────────────────

    def schedule_task(task_id: int, when: str) -> dict[str, Any]:
        return patch(task_id, when_fields(when))

    def complete_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"completed": True})

    def reopen_task(task_id: int) -> dict[str, Any]:
        # Clear both completion and cancellation: a task can come back from either.
        return patch(task_id, {"completed": False, "canceled": False})

    def log_task(task_id: int) -> dict[str, Any]:
        task = task_by_id(api.state(), task_id)
        if not is_finished(task):
            raise NuvoError(
                f"'{task['title']}' is not finished yet. The Logbook is where closed tasks "
                "go: run complete_task first, or the task would simply vanish from sight."
            )
        return patch(task_id, {"logged": True})

    def trash_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"trashed": True})

    def restore_task(task_id: int) -> dict[str, Any]:
        return patch(task_id, {"trashed": False})

    # ─── checklist ────────────────────────────────────────────────────────────

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
            names = ", ".join(f"'{item['title']}'" for item in items)
            raise NuvoError(
                f"The checklist has no item '{title}'. It has: {names or 'none at all'}."
            )
        if len(hits) > 1:
            names = ", ".join(f"'{item['title']}'" for item in hits)
            raise NuvoError(f"'{title}' matches more than one item: {names}.")
        hits[0]["completed"] = done
        return patch(task_id, {"checklist": items})

    # ─── tags ─────────────────────────────────────────────────────────────────

    def tag_task(task_id: int, tag: str) -> dict[str, Any]:
        state = api.state()
        task = task_by_id(state, task_id)
        found = find_by_title(state["tags"], tag)
        # The tag may not exist — create it. The request is idempotent: the
        # server returns the existing one if it was there after all.
        row = found or api.call("POST", "/api/tags", json={"title": tag})
        ids = {item["id"] for item in task["tags"]} | {row["id"]}
        return patch(task_id, {"tag_ids": sorted(ids)})

    def untag_task(task_id: int, tag: str) -> dict[str, Any]:
        state = api.state()
        task = task_by_id(state, task_id)
        ids = [item["id"] for item in task["tags"] if item["title"].lower() != tag.lower()]
        if len(ids) == len(task["tags"]):
            raise NuvoError(f"Task '{task['title']}' did not have the tag '{tag}' to begin with.")
        return patch(task_id, {"tag_ids": ids})

    # ─── projects and areas ───────────────────────────────────────────────────

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


#: The model reads these descriptions, so they say not "what the function does"
#: but "when to call it": the name `log_task` alone is not enough to choose by.
DESCRIPTIONS = {
    "list_lists": (
        "Everything the person already has: projects, areas, tags and saved filters, "
        "by name only. Call this first if you don't know where a task belongs or which "
        "tags exist."
    ),
    "list_tasks": (
        "Tasks filtered by the 'when' field (today, evening, anytime, someday, scheduled), "
        "by project or by tag. With no filter — every open task. Finished ones show up only "
        "on request (include_done)."
    ),
    "today": (
        "The main question of the day in one call: what is on for today and what is past its "
        "deadline. Call it for 'what do I have today', 'what's urgent', 'where do I start'. "
        "Finished tasks never appear here."
    ),
    "search_tasks": (
        "Find a task by words from its title or notes. Call it before creating a task: that "
        "way a second 'Call the doctor' never lands next to the first."
    ),
    "get_task": (
        "One task in full: notes, checklist, tags, project, dates and state. "
        "Call it before editing notes or a checklist — so you know what is already there."
    ),
    "create_task": (
        "Create a new task. `when`: today — Today, evening — This Evening, anytime — "
        "Anytime (the default), someday — Someday, or a YYYY-MM-DD date. "
        "`deadline` is the last possible day, which is not the day you'll do it. "
        "Run search_tasks first: a duplicate is worse than nothing."
    ),
    "update_task": (
        "Rewrite the title, the whole note or the deadline; `clear_deadline=true` removes the "
        "deadline altogether. Notes almost always want appending rather than rewriting — "
        "add_note is there for that. The day and the 'when' are changed by schedule_task."
    ),
    "add_note": (
        "Append a paragraph stamped with today's date to a task's notes, leaving what was "
        "written earlier untouched. This is the local stand-in for comments: how a "
        "conversation ended, what turned up, what was decided."
    ),
    "move_task": (
        "Move a task into a project or into an area. With neither of them given, the task "
        "goes to the Inbox. A new project is created with create_project."
    ),
    "schedule_task": (
        "Set when to get to a task: today — Today, evening — This Evening, "
        "anytime — Anytime, someday — Someday (park it), or a YYYY-MM-DD date. "
        "Give Today only to what the person is really taking on today: an overfull day "
        "stops being read."
    ),
    "complete_task": "Mark the task done. A repeating one spawns its next occurrence itself.",
    "reopen_task": (
        "Put the task back to work: clears the done mark, the cancellation and the filing in "
        "the Logbook. Call it if the task was finished by mistake or has come back."
    ),
    "log_task": (
        "File a finished task in the Logbook so it leaves the lists. An unfinished one "
        "cannot be filed — run complete_task first."
    ),
    "trash_task": (
        "Throw the task into the Trash. Reversible: restore_task brings it back. The agent "
        "has no permanent delete on purpose — emptying the trash is the person's own call."
    ),
    "restore_task": "Take a task out of the Trash and back into work.",
    "add_checklist_item": (
        "Add an item to a task's checklist — a small step inside a single task. "
        "If there are more than a dozen steps, or they have deadlines of their own, "
        "that is a project, not a checklist."
    ),
    "check_checklist_item": (
        "Tick a checklist item off (or untick it with done=false). "
        "The item is found by title, and a fragment is enough — as long as only one matches."
    ),
    "tag_task": (
        "Put a tag on the task. If no such tag exists yet, it is created. The task's other "
        "tags stay where they are."
    ),
    "untag_task": "Take a tag off the task. The other tags stay.",
    "create_project": (
        "Create a project — a piece of work of several steps with a list of its own. It can "
        "go straight into an area. Check list_lists first: a project by that name may "
        "already exist."
    ),
    "create_area": (
        "Create an area — a standing part of life or work ('Home', 'Health') that projects "
        "and tasks live in. People keep only a handful of areas; usually a project is what "
        "is wanted."
    ),
}
