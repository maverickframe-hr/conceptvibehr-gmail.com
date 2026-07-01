# hr-bridge plugin (source of truth)

Постоянный исходник Cowork-плагина `hr-bridge` (коннектор к HH.ru / Rabota.by).

## Что здесь

- `servers/server.py` — MCP-сервер плагина. Содержит инструмент **`change_status`**
  (смена статуса отклика, включая «Отказ») в дополнение к чтению откликов, резюме,
  чатов и отправке сообщений/Telegram.
- `skills/hr-chats/SKILL.md` — скилл с постоянными правилами работы с рабочими сайтами
  (см. также `RULES_job_sites.md`).
- `RULES_job_sites.md` — свод правил (согласие владельца, защита от необратимых действий и т.д.).

## Как сделать изменения «живыми»

Бэкенд (`maverickframe-hh-bridge.onrender.com`) уже поддерживает смену статуса —
менять его не нужно. Чтобы новый tool и правило подхватились в Cowork:

1. Заменить в установленном плагине `hr-bridge` файлы `servers/server.py` и
   `skills/hr-chats/SKILL.md` на версии отсюда.
2. Переустановить / обновить плагин в Cowork (Settings → Capabilities).

До переустановки смену статуса можно делать через скрипт `hr_status.py` или прямым
`POST` на `/{provider}/negotiations/{nid}/change_state` — это работает уже сейчас.

## Действия статусов

`discard_by_employer` (Отказ), `consider`, `phone_interview`, `interview`, `assessment`,
`offer`, `hired`, `discard_no_interaction`, `discard_vacancy_closed`.
