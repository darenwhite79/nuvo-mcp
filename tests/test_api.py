"""Ошибки клиента: человек должен узнать, что чинить, а не увидеть трейсбек."""

import httpx
import pytest

from nuvo_mcp.api import NuvoApi, NuvoError


def api_answering(handler) -> NuvoApi:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://nuvo.test")
    return NuvoApi("http://nuvo.test", "nv_test", client=client)


def test_молчащий_сервер_называет_адрес_и_способ_поднять():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(NuvoError) as error:
        api_answering(refuse).state()

    assert "http://nuvo.test" in str(error.value)
    assert "make api" in str(error.value)


def test_отзыв_ключа_говорит_куда_идти_за_новым():
    api = api_answering(lambda request: httpx.Response(401, json={"detail": "Ключ неизвестен"}))

    with pytest.raises(PermissionError) as error:
        api.state()

    assert "NUVO_TOKEN" in str(error.value)


def test_нехватка_права_называет_список_прав():
    api = api_answering(lambda request: httpx.Response(403, json={"detail": "нет права"}))

    with pytest.raises(PermissionError) as error:
        api.call("POST", "/api/tasks", json={"title": "Нельзя"})

    assert "read, create, edit, delete" in str(error.value)


def test_отказ_приложения_пересказывается_его_словами():
    api = api_answering(lambda request: httpx.Response(409, json={"detail": "Сначала в корзину"}))

    with pytest.raises(NuvoError) as error:
        api.call("DELETE", "/api/tasks/1")

    assert "Сначала в корзину" in str(error.value)
    assert "409" in str(error.value)


def test_проверка_связи_молчит_когда_всё_цело():
    api = api_answering(lambda request: httpx.Response(200, json={"status": "ok"}))

    assert api.reachable() is None


def test_проверка_связи_отличает_чужой_сервер_от_молчания():
    api = api_answering(lambda request: httpx.Response(404, text="Not Found"))

    assert "это не Nuvo" in (api.reachable() or "")


def test_ключ_с_кириллицей_не_уходит_в_заголовок():
    with pytest.raises(NuvoError) as error:
        NuvoApi("http://nuvo.test", "nv_ключ")

    assert "нелатинские" in str(error.value)
