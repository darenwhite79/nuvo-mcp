"""Client errors: the person has to learn what to fix, not to see a traceback."""

import httpx
import pytest

from nuvo_mcp.api import NuvoApi, NuvoError


def api_answering(handler) -> NuvoApi:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://nuvo.test")
    return NuvoApi("http://nuvo.test", "nv_test", client=client)


def test_a_silent_server_names_the_address_and_how_to_start_it():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(NuvoError) as error:
        api_answering(refuse).state()

    assert "http://nuvo.test" in str(error.value)
    assert "make api" in str(error.value)


def test_a_revoked_key_says_where_to_get_a_new_one():
    api = api_answering(lambda request: httpx.Response(401, json={"detail": "Unknown key"}))

    with pytest.raises(PermissionError) as error:
        api.state()

    assert "NUVO_TOKEN" in str(error.value)


def test_a_missing_right_names_the_list_of_rights():
    api = api_answering(lambda request: httpx.Response(403, json={"detail": "no right"}))

    with pytest.raises(PermissionError) as error:
        api.call("POST", "/api/tasks", json={"title": "Not allowed"})

    assert "read, create, edit, delete" in str(error.value)


def test_a_refusal_from_the_app_is_retold_in_its_own_words():
    api = api_answering(
        lambda request: httpx.Response(409, json={"detail": "Move it to the trash first"})
    )

    with pytest.raises(NuvoError) as error:
        api.call("DELETE", "/api/tasks/1")

    assert "Move it to the trash first" in str(error.value)
    assert "409" in str(error.value)


def test_the_connection_check_stays_quiet_when_all_is_well():
    api = api_answering(lambda request: httpx.Response(200, json={"status": "ok"}))

    assert api.reachable() is None


def test_the_connection_check_tells_a_stranger_from_silence():
    api = api_answering(lambda request: httpx.Response(404, text="Not Found"))

    assert "it is not Nuvo" in (api.reachable() or "")


def test_a_non_ascii_key_never_reaches_the_header():
    with pytest.raises(NuvoError) as error:
        NuvoApi("http://nuvo.test", "nv_clé")

    assert "non-ASCII" in str(error.value)
