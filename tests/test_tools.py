"""The tools: what exactly goes to the API and how the snapshot is parsed."""

from datetime import date

import pytest
from conftest import item, snapshot, task

from nuvo_mcp.api import NuvoError
from nuvo_mcp.tools import day_view, make_tools, tasks_of, with_date

TODAY = date(2026, 9, 3)


# ─── parsing the snapshot ─────────────────────────────────────────────────────


def test_today_gathers_the_started_and_the_overdue():
    state = snapshot(
        tasks=[
            task(id=1, title="Marked for today", when_kind="today"),
            task(id=2, title="This evening", when_kind="evening"),
            task(id=3, title="The day has come", when_kind="scheduled", when_date="2026-09-01"),
            task(id=4, title="The day is ahead", when_kind="scheduled", when_date="2026-09-10"),
            task(id=5, title="Someday", when_kind="someday"),
            task(id=6, title="The deadline has passed", deadline="2026-08-30"),
        ]
    )

    view = day_view(state, TODAY)

    assert [t["title"] for t in view["today"]] == [
        "Marked for today",
        "This evening",
        "The day has come",
    ]
    assert [t["title"] for t in view["overdue"]] == ["The deadline has passed"]
    assert view["date"] == "2026-09-03"


def test_today_says_nothing_about_the_closed_and_the_thrown_away():
    state = snapshot(
        tasks=[
            task(id=1, title="Done", when_kind="today", completed_at="2026-09-03T09:00:00Z"),
            task(id=2, title="In the trash", when_kind="today", trashed_at="2026-09-03T09:00:00Z"),
            task(id=3, title="In the logbook", when_kind="today", logged_at="2026-09-03T09:00:00Z"),
            task(id=4, title="Still open", when_kind="today"),
        ]
    )

    assert [t["title"] for t in day_view(state, TODAY)["today"]] == ["Still open"]


def test_the_project_and_tag_filters_ignore_case():
    state = snapshot(
        projects=[{"id": 5, "title": "Renovation", "trashed_at": None}],
        tasks=[
            task(id=1, title="Buy paint", project_id=5, tags=[{"id": 9, "title": "home"}]),
            task(id=2, title="Something unrelated"),
        ],
    )

    assert [t["title"] for t in tasks_of(state, project="rEnOvAtIoN")] == ["Buy paint"]
    assert [t["title"] for t in tasks_of(state, tag="HOME")] == ["Buy paint"]
    assert tasks_of(state)[0]["project"] == "Renovation"


def test_a_note_is_appended_with_a_date_and_keeps_what_was_there():
    before = "The first conversation"

    after = with_date(before, "Call back on Thursday", TODAY)

    assert after == "The first conversation\n\n**2026-09-03** — Call back on Thursday"
    assert with_date("", "The beginning", TODAY) == "**2026-09-03** — The beginning"


# ─── what goes to the API ─────────────────────────────────────────────────────


def test_a_date_instead_of_a_word_means_scheduled(fake):
    stand = fake(tasks=[task(id=1)])

    make_tools(stand.api)["schedule_task"](task_id=1, when="2026-12-31")

    assert stand.last.body == {"when_kind": "scheduled", "when_date": "2026-12-31"}


def test_the_word_someday_goes_through_as_it_is(fake):
    stand = fake(tasks=[task(id=1)])

    make_tools(stand.api)["schedule_task"](task_id=1, when="someday")

    assert stand.last.body == {"when_kind": "someday"}


def test_a_malformed_date_explains_the_format(fake):
    tools = make_tools(fake(tasks=[task(id=1)]).api)

    with pytest.raises(NuvoError) as error:
        tools["schedule_task"](task_id=1, when="31.12.2026")

    assert "YYYY-MM-DD" in str(error.value)


def test_add_note_sends_the_whole_note(fake):
    stand = fake(tasks=[task(id=1, notes="The old text")])

    make_tools(stand.api)["add_note"](task_id=1, text="The new text")

    assert stand.last.path == "/api/tasks/1"
    assert stand.last.body["notes"].startswith("The old text\n\n**")
    assert stand.last.body["notes"].endswith("— The new text")


def test_a_checklist_item_is_added_to_the_existing_ones(fake):
    stand = fake(tasks=[task(id=1, checklist=[item("First", completed=True)])])

    make_tools(stand.api)["add_checklist_item"](task_id=1, title="Second")

    assert stand.last.body["checklist"] == [
        {"title": "First", "completed": True},
        {"title": "Second", "completed": False},
    ]


def test_an_item_is_found_by_part_of_its_title(fake):
    stand = fake(
        tasks=[task(id=1, checklist=[item("Call the bank"), item("Pick up the certificate")])]
    )

    make_tools(stand.api)["check_checklist_item"](task_id=1, title="bank")

    assert stand.last.body["checklist"] == [
        {"title": "Call the bank", "completed": True},
        {"title": "Pick up the certificate", "completed": False},
    ]


def test_an_ambiguous_item_is_not_ticked_at_random(fake):
    tools = make_tools(fake(tasks=[task(id=1, checklist=[item("Call A"), item("Call B")])]).api)

    with pytest.raises(NuvoError) as error:
        tools["check_checklist_item"](task_id=1, title="Call")

    assert "more than one" in str(error.value)


def test_a_new_tag_does_not_knock_off_the_old_ones(fake):
    stand = fake(tasks=[task(id=1, tags=[{"id": 3, "title": "home"}])], tags=[])

    make_tools(stand.api)["tag_task"](task_id=1, tag="urgent")

    assert stand.sent[0].path == "/api/tags"
    assert stand.last.body == {"tag_ids": [3, 77]}


def test_a_known_tag_is_not_created_again(fake):
    stand = fake(tasks=[task(id=1)], tags=[{"id": 3, "title": "Home", "position": 0}])

    make_tools(stand.api)["tag_task"](task_id=1, tag="home")

    assert [sent.path for sent in stand.sent] == ["/api/tasks/1"]
    assert stand.last.body == {"tag_ids": [3]}


def test_the_logbook_takes_no_unfinished_task(fake):
    tools = make_tools(fake(tasks=[task(id=1, title="Still in progress")]).api)

    with pytest.raises(NuvoError) as error:
        tools["log_task"](task_id=1)

    assert "complete_task" in str(error.value)


def test_a_finished_task_goes_to_the_logbook(fake):
    stand = fake(tasks=[task(id=1, completed_at="2026-09-03T09:00:00Z")])

    make_tools(stand.api)["log_task"](task_id=1)

    assert stand.last.body == {"logged": True}


def test_moving_into_an_area_takes_the_task_out_of_its_project(fake):
    stand = fake(
        areas=[{"id": 4, "title": "Home", "trashed_at": None}],
        tasks=[task(id=1, project_id=2)],
    )

    make_tools(stand.api)["move_task"](task_id=1, area="Home")

    assert stand.last.body == {"area_id": 4, "clear_project": True}


def test_moving_with_no_destination_returns_the_task_to_the_inbox(fake):
    stand = fake(tasks=[task(id=1, project_id=2)])

    make_tools(stand.api)["move_task"](task_id=1)

    assert stand.last.body == {"clear_project": True, "clear_area": True}


def test_a_missing_project_names_the_ones_that_exist(fake):
    tools = make_tools(fake(projects=[{"id": 5, "title": "Renovation", "trashed_at": None}]).api)

    with pytest.raises(NuvoError) as error:
        tools["create_task"](title="A task", project="Renovaton")

    assert "'Renovation'" in str(error.value)


def test_the_search_looks_into_the_notes_too(fake):
    stand = fake(
        tasks=[
            task(id=1, title="Call back", notes="about the contract"),
            task(id=2, title="Contract for the flat"),
            task(id=3, title="Something unrelated"),
        ]
    )

    found = make_tools(stand.api)["search_tasks"](query="contract")

    assert [t["id"] for t in found] == [1, 2]


def test_removing_a_tag_that_was_never_there_says_so_plainly(fake):
    tools = make_tools(fake(tasks=[task(id=1, title="A task")]).api)

    with pytest.raises(NuvoError) as error:
        tools["untag_task"](task_id=1, tag="home")

    assert "to begin with" in str(error.value)


def test_every_tool_has_a_description(fake):
    from nuvo_mcp.tools import DESCRIPTIONS

    assert set(make_tools(fake().api)) == set(DESCRIPTIONS)


def test_a_trashed_project_takes_no_new_tasks(fake):
    tools = make_tools(
        fake(
            projects=[
                {"id": 5, "title": "Renovation", "trashed_at": "2026-09-01T10:00:00Z"},
                {"id": 6, "title": "Vacation", "trashed_at": None},
            ]
        ).api
    )

    with pytest.raises(NuvoError) as error:
        tools["create_task"](title="Buy paint", project="Renovation")

    # The name is reported as missing, and it is already gone from the live list.
    assert str(error.value).startswith("There is no project 'Renovation'.")
    assert "There is: 'Vacation'." in str(error.value)
