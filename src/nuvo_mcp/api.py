"""Клиент к HTTP-API Nuvo.

Сервер не ходит в базу напрямую намеренно: иначе правила прав, журнал действий
и проверки разошлись бы на два пути, и агент получил бы лазейку мимо ключа.

Ошибки переводятся на человеческий язык прямо здесь. Агент показывает текст
исключения дословно, поэтому «ConnectError('[Errno 61] Connection refused')»
означало бы, что человек так и не узнал, что чинить.
"""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError


class NuvoError(ToolError):
    """Сбой, о котором агент обязан узнать словами.

    Наследование от `ToolError` — не украшение: всё остальное MCP считает
    падением инструмента и заменяет текст на «Error executing tool …». То есть
    любое другое исключение стоило бы нам ровно того, ради чего эти сообщения и
    писались.
    """


class NoRight(NuvoError, PermissionError):
    """Ключу не хватает права. Отдельный вид: чинится не повтором, а новым
    ключом, и вызывающему полезно отличать это от прочих отказов."""


class NuvoApi:
    """Клиент к своему же API. Права проверяет сервер, а не эта обёртка."""

    def __init__(
        self,
        base_url: str,
        token: str,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        # Заголовок кодируется латиницей. Настоящий ключ — `nv_` и случайные
        # безопасные символы, но в переменную окружения попадает и опечатка: без
        # этой проверки она вылезла бы UnicodeEncodeError глубоко внутри httpx.
        if not token.isascii():
            raise NuvoError(
                "NUVO_TOKEN содержит нелатинские символы. Ключ выглядит как "
                "«nv_» и набор латинских букв и цифр — похоже, скопировалось лишнее."
            )
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(
                method, path, headers={"Authorization": f"Bearer {self.token}"}, **kwargs
            )
        except httpx.TimeoutException as error:
            raise NuvoError(
                f"Nuvo не ответила за отведённое время ({self.base_url}). "
                "Похоже, сервер занят или адрес ведёт не туда."
            ) from error
        except httpx.RequestError as error:
            raise NuvoError(
                f"Nuvo не отвечает по адресу {self.base_url}. Проверьте, что приложение "
                "запущено (`make api`), и что NUVO_URL указывает на него."
            ) from error

        if response.status_code == 401:
            raise NoRight(
                "Ключ неизвестен или отозван. Выдайте новый на экране «Подключение» "
                "и положите его в NUVO_TOKEN."
            )
        if response.status_code == 403:
            raise NoRight(
                f"У ключа нет права на это действие: {method} {path}. "
                "Права выдаются при создании ключа: read, create, edit, delete."
            )
        if response.status_code >= 400:
            raise NuvoError(f"Nuvo отказала ({response.status_code}): {detail_of(response)}")
        return response.json() if response.content else None

    def state(self) -> dict[str, Any]:
        """Снимок целиком: области, проекты, заголовки, дела, теги, отборы."""

        return self.call("GET", "/api/state")

    def reachable(self) -> str | None:
        """Проверка связи при старте. Возвращает жалобу или None, если всё цело.

        Берётся открытый маршрут: он не требует ключа, не пишется в журнал и не
        тянет снимок целиком. Годность самого ключа выяснится на первом же
        вызове инструмента — и скажет об этом внятно.
        """

        try:
            response = self._client.get("/api/health", timeout=5.0)
        except httpx.RequestError:
            return (
                f"Nuvo не отвечает по адресу {self.base_url}. Инструменты будут возвращать "
                "ошибку, пока приложение не поднимется. Запуск: make api"
            )
        if response.status_code != 200:
            return (
                f"По адресу {self.base_url} что-то отвечает, но это не Nuvo: "
                f"/api/health вернул {response.status_code}."
            )
        return None


def detail_of(response: httpx.Response) -> str:
    """Пояснение из тела ответа. FastAPI кладёт его в `detail`."""

    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or "сервер промолчал"
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return str(body)[:200]
