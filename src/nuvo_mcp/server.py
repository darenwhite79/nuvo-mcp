"""Сборка и запуск MCP-сервера.

Транспорт — stdio: канал занят протоколом целиком, поэтому всё, что пишется
человеку, уходит в stderr. Строка в stdout сломала бы разговор с клиентом.

Запуск:
    NUVO_TOKEN=nv_… uvx nuvo-mcp
"""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer

from nuvo_mcp.api import NuvoApi, NuvoError
from nuvo_mcp.tools import DESCRIPTIONS, make_tools

DEFAULT_URL = "http://127.0.0.1:8000"

#: Читает модель, когда решает, звать ли этот сервер вообще.
INSTRUCTIONS = """\
Nuvo — менеджер дел: область → проект → дело, плюс чек-лист и теги.

Как здесь принято:
- «Сегодня» — обещание сделать сегодня, а не пометка важности. Ставьте его
  только тому, за что человек берётся сегодня.
- Срок (deadline) и день выполнения — разные вещи: срок говорит «после этого
  поздно», день говорит «займусь тогда-то».
- Отдельных комментариев нет: их место — заметка дела, куда add_note дописывает
  абзац с датой, ничего не затирая.
- Перед созданием дела ищите похожее через search_tasks: дубликат хуже, чем
  ничего.
- Окончательного удаления у агента нет намеренно. Корзину чистит человек.

Сервер ходит в то же HTTP-API, что и приложение, поэтому подчиняется правам
ключа, а всё сделанное видно в журнале ключа.
"""

NO_TOKEN = """\
Не задан NUVO_TOKEN — без ключа доступа Nuvo не пустит.

Где взять: откройте приложение → «Настройки» → «Подключение», выдайте ключ с
правами «Читать», «Создавать», «Изменять». Токен показывается один раз.

Без интерфейса ключ выдаёт и сам API, локально и без ключа:
    curl -X POST http://127.0.0.1:8000/api/keys \\
      -H 'Content-Type: application/json' \\
      -d '{"title":"Мой агент","scopes":"read,create,edit"}'

Затем положите его в настройку своего клиента:
    "env": { "NUVO_TOKEN": "nv_…", "NUVO_URL": "http://127.0.0.1:8000" }
"""


def build_server(api: NuvoApi) -> MCPServer:
    server = MCPServer(name="nuvo", version="0.1.0", instructions=INSTRUCTIONS)
    for name, function in make_tools(api).items():
        server.tool(name=name, description=DESCRIPTIONS[name])(function)
    return server


def main() -> None:
    token = os.environ.get("NUVO_TOKEN", "").strip()
    if not token:
        raise SystemExit(NO_TOKEN)

    try:
        api = NuvoApi(os.environ.get("NUVO_URL", "").strip() or DEFAULT_URL, token)
    except NuvoError as error:
        # Настройка разобрана неверно — это разговор с человеком, а не сбой
        # программы: трейсбек тут только мешает прочитать, что чинить.
        raise SystemExit(str(error)) from None

    # Жалуемся, но не падаем: клиент запускает сервер вместе с редактором, а
    # приложение человек поднимает когда придётся. Упасть здесь значило бы
    # требовать перезапуска редактора ради порядка запуска.
    complaint = api.reachable()
    if complaint:
        print(complaint, file=sys.stderr, flush=True)

    build_server(api).run(transport="stdio")


if __name__ == "__main__":
    main()
