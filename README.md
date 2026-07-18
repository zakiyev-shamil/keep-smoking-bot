# Office Party Telegram Bot

Telegram-first бот для закрытых офисных Party. Участник создаёт универсальное событие,
коллеги получают личное уведомление и отвечают `GOING`, `LATER` или `DECLINED`.
Для обеда создатель при желании добавляет общий inline-опрос на 2–6 вариантов.

```text
User → Party → Event → Notification → EventResponse
```

В текущем интерфейсе оставлены перекур, обед и кастомное событие. Модель и сервисы не
завязаны на курилку и поддерживают другие `EventType`.

## Архитектура

```text
api/index.py       FastAPI webhook для Vercel
app/
  bot/             aiogram handlers, callbacks, keyboards, FSM, тексты
  core/            config, enums, exceptions, logging, UTC helpers
  database/        async SQLAlchemy session и PostgreSQL FSM storage
  models/          SQLAlchemy models
  repositories/    явные persistence-операции
  services/        транзакции и domain rules
  workers/         controlled notification fan-out и local expiration loop
  main.py          long polling для локальной разработки
alembic/            миграции
tests/              unit и state-machine tests
```

PostgreSQL — единственный source of truth. В нём хранятся данные, FSM, выбранная Party,
ссылка на последнее сообщение создателя и агрегированные голоса обеденного опроса.
Дубли событий защищены транзакционным advisory lock и partial unique index. Redis для
MVP до 20 человек не нужен.

На Vercel уведомления выполняются внутри webhook-запроса с bounded concurrency и rate
limiter. Результаты доставки сохраняются в `notifications`, поэтому повторная доставка
update не создаёт повторную рассылку. Локальный polling использует небольшую async queue.

## Быстрый локальный запуск

Нужны Docker Compose и Telegram bot token от `@BotFather`.

```bash
cp .env.example .env
# заполнить BOT_TOKEN и BOT_USERNAME
docker compose up --build
```

Compose поднимает bot и PostgreSQL, применяет `alembic upgrade head` и запускает polling.

## Бесплатный production: Vercel + Neon

### 1. Neon

Создайте PostgreSQL в ближайшем регионе. Neon Auth включать не нужно. Скопируйте
**pooled connection string**: hostname должен содержать `-pooler`. Direct URL нужен
только для Alembic.

### 2. Vercel

Импортируйте GitHub-репозиторий как новый Project. Framework Preset можно оставить
`Other`; Build/Output settings менять не нужно.

В `Settings → Environment Variables` добавьте для `Production`, `Preview` и
`Development`:

- `BOT_TOKEN` — token из BotFather;
- `BOT_USERNAME` — username бота без `@`;
- `DATABASE_URL` — pooled Neon connection string целиком;
- `WEBHOOK_SECRET` — случайная строка, например результат `openssl rand -hex 32`;
- `DEFAULT_TIMEZONE` — `Asia/Almaty`;
- `SMOKE_COOLDOWN_MINUTES` — `0`;
- `LOG_LEVEL` — `INFO`.

`DATABASE_URL` можно вставлять в формате Neon
`postgresql://...?sslmode=require&channel_binding=require`: config автоматически
преобразует его для `asyncpg`.

В `vercel.json` явно включён Fluid Compute и закреплён `fra1`. Runtime переиспользует
небольшой SQLAlchemy pool (`3 + 2 overflow`, timeout `5 с`, recycle `240 с`), поэтому
production `DATABASE_URL` обязательно должен оставаться pooled. Fluid Compute сокращает
cold start, но бесплатный serverless не гарантирует его полного отсутствия.

### 3. Миграции Neon

Один раз из checkout репозитория. Для миграции лучше скопировать из Neon **direct
connection string** (без `-pooler`), а приложение в Vercel продолжает использовать pooled:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e .
export DATABASE_URL='PASTE_NEON_DIRECT_URL_HERE'
.venv/bin/alembic upgrade head
unset DATABASE_URL
```

Не сохраняйте production connection string в Git и не отправляйте его в чат.

Порядок production-выпуска:

1. Убедиться, что Vercel `DATABASE_URL` — pooled URL с `-pooler`.
2. Выполнить `alembic upgrade head` с direct URL без `-pooler`.
3. Развернуть приложение и проверить сценарий создатель + два участника.

### 4. Webhook Telegram

После production deploy возьмите URL вида `https://project.vercel.app`. В локальном
`.env` должны быть те же `BOT_TOKEN` и `WEBHOOK_SECRET`, затем:

```bash
WEBHOOK_BASE_URL=https://project.vercel.app .venv/bin/python scripts/set_webhook.py
```

Проверка:

```bash
curl https://project.vercel.app/api/health
curl https://project.vercel.app/api/health/database
```

Второй endpoint дополнительно проверяет pooled runtime-соединение и актуальную Alembic
revision. После этого отправьте боту `/start`.

Важно: одновременно должен работать только один способ получения updates. После включения
webhook остановите локальный polling-контейнер:

```bash
docker compose stop bot
```

## Environment variables

Обязательные:

- `BOT_TOKEN`
- `DATABASE_URL`
- `WEBHOOK_SECRET` — обязателен для Vercel webhook

Основные дополнительные:

- `BOT_USERNAME`
- `LOG_LEVEL`
- `DEFAULT_TIMEZONE`
- `<TYPE>_EVENT_TTL_MINUTES`
- `<TYPE>_COOLDOWN_MINUTES`
- `NOTIFICATION_CONCURRENCY`
- `INVITATION_REFRESH_CONCURRENCY` (по умолчанию `5`)
- `NOTIFICATION_RATE_PER_SECOND`
- `NOTIFY_ON_EVENT_STARTED`
- `NOTIFY_ON_EVENT_CANCELLED`

Полный список находится в `.env.example`. Все timestamp хранятся в UTC.

## Миграции и локальная разработка

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
docker compose up -d postgres
```

Для запуска Python на host замените hostname `postgres` в `DATABASE_URL` на `localhost`,
после чего:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.main
```

Новые изменения схемы создаются только миграциями:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Команды и UX

- `/start` — регистрация или вступление по invite deep-link;
- `/menu` и `/party` — главное меню;
- `/help` — помощь.

Остальные действия выполняются кнопками. FSM нужен только для названия Party и custom
event.

## Проверки

```bash
ruff format --check .
ruff check .
pytest
```

Тесты покрывают Party, idempotency, duplicate protection, cooldown, expiration, response
и poll upsert, permissions, filtering, PostgreSQL FSM, Alembic upgrade/check/downgrade и
случайные последовательности domain-команд через Hypothesis.

В structured logs есть `event_response_pipeline_timing` с этапами `db_ms`,
`actor_edit_ms`, `status_notification_ms`, `invitation_refresh_ms`, а Vercel webhook
пишет `vercel_invocation_*` с признаком `cold`/`warm`. Для тёплого изменения сообщения
автора целевой ориентир — менее `1 с`; редкие cold start остаются ограничением выбранного
serverless-варианта.

## Ограничения Telegram

Бот может написать только пользователю, который раньше открыл его. При
`TelegramForbiddenError` пользователь отмечается `bot_accessible=false`; его ошибка не
останавливает рассылку остальным.
