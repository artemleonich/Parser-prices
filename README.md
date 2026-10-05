<p align="center">
  <a href=".github/assets/light/mark.svg#gh-light-mode-only"><img src=".github/assets/light/mark.svg" width="40" height="40" alt="PriceRadar" /></a><a href=".github/assets/mark.svg#gh-dark-mode-only"><img src=".github/assets/mark.svg" width="40" height="40" alt="PriceRadar" /></a>
</p>

<h1 align="center">PriceRadar</h1>

<p align="center"><strong>Цены меняются. PriceRadar следит за ними.</strong></p>

<p align="center">
  <a href=".github/assets/light/stack.svg#gh-light-mode-only"><img src=".github/assets/light/stack.svg" height="28" alt="Python · FastAPI · PostgreSQL · Docker" /></a><a href=".github/assets/stack.svg#gh-dark-mode-only"><img src=".github/assets/stack.svg" height="28" alt="Python · FastAPI · PostgreSQL · Docker" /></a>
</p>

MVP сервиса мониторинга Wildberries, Ozon и Яндекс Маркета: Telegram-бот, история цен, веб-дашборд и уведомления по правилам.

[Запуск](#запуск-с-docker) · [Конфигурация](#конфигурация) · [Тарифы](#настройки-тарифов) · [Тесты](#тесты) · [English](#english)

## Возможности

- **Три маркетплейса:** отдельные парсеры Wildberries, Ozon и Яндекс Маркета.
- **Telegram-бот:** добавление товаров и управление уведомлениями.
- **История цен:** графики, минимальная цена и динамика в веб-дашборде.
- **Уведомления:** снижение или повышение цены, достижение целевой цены и возврат в наличие.
- **Фоновые задачи:** обновление цен, проверка уведомлений и очистка истории через Celery.
- **Free / Basic / Pro:** ограничения товаров, уведомлений и истории; интеграция подписок с YooKassa.

## Стек

Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL · Redis · Celery · aiogram 3 · Jinja2 / HTMX · httpx · Playwright · Alembic · Docker Compose.

## Запуск с Docker

Нужны Git, Docker с Compose, токен Telegram-бота и параметры YooKassa, которые требует текущая конфигурация.

### 1. Подготовьте окружение

```bash
git clone https://github.com/artemleonich/Parser-prices.git
cd Parser-prices/priceradar
cp .env.example .env
```

Замените примеры в `.env`: `DB_PASSWORD` и пароль в обоих `DATABASE_URL`, токен и имя бота, параметры YooKassa и `SECRET_KEY`. Для `SECRET_KEY` нужен случайный секрет длиной не менее 32 символов. Значения `changeme` и `supersecretkey` отвергаются валидатором.

### 2. Запустите БД и примените миграции

```bash
docker compose up -d db redis
docker compose run --rm app alembic upgrade head
```

### 3. Запустите приложение, бот и фоновые задачи

```bash
docker compose up -d --build
```

Дашборд: [localhost:8000/dashboard](http://localhost:8000/dashboard). Страницы требуют авторизации; её обработчик расположен в [app/api/auth.py](priceradar/app/api/auth.py). В настроенном Telegram-боте отправьте `/start`.

Compose запускает приложение с `--reload` и монтирует исходники — это окружение для разработки. Для публичного сервиса нужно отдельно подготовить развёртывание и проверить авторизацию, платежи и поведение парсеров.

## Конфигурация

Примеры — в [priceradar/.env.example](priceradar/.env.example), проверка параметров — в [app/config.py](priceradar/app/config.py).

| Переменная | Назначение |
| --- | --- |
| `DATABASE_URL` / `DATABASE_URL_SYNC` | Асинхронное подключение приложения / миграции |
| `DB_PASSWORD` | Пароль PostgreSQL в Compose |
| `REDIS_URL` | Брокер и хранилище результатов Celery |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | Telegram-бот |
| `YUKASSA_SHOP_ID` / `YUKASSA_SECRET_KEY` | Интеграция оплаты |
| `SECRET_KEY` | Секрет приложения |
| `BASE_URL` | Адрес приложения |
| `PROXY_LIST` | Необязательный список прокси через запятую |

```dotenv
PROXY_LIST=http://user1:pass@proxy1:8080,http://user2:pass@proxy2:8080
```

Парсеры работают с внешними площадками: изменение API, HTML или блокировки могут потребовать их обновления.

## Настройки тарифов

Значения ниже заданы в [models/user.py](priceradar/app/models/user.py), [config.py](priceradar/app/config.py) и [subscription_service.py](priceradar/app/services/subscription_service.py). Это конфигурация MVP.

| Параметр | Free | Basic | Pro |
| --- | --- | --- | --- |
| Цена за 30 дней в коде | 0 ₽ | 990 ₽ | 2 490 ₽ |
| Товары | 5 | 50 | 200 |
| Маркетплейсы | 1 | 3 | 3 |
| История | 7 дней | 30 дней | 90 дней |
| Уведомления | 3 | 20 | 999 999 |
| Минимальный интервал в конфигурации | 2 часа | 30 минут | 15 минут |

Планировщик сейчас отбирает товары **раз в 30 минут**, поэтому настройка Pro «15 минут» сама по себе не обеспечивает обновление с такой частотой. Очистка истории использует общий предел Pro — 90 дней.

## Запуск без Docker

Установите Python 3.12, PostgreSQL и Redis. В `.env` замените имена Compose-хостов `db` и `redis` на адреса своих сервисов.

Из каталога `priceradar`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
alembic upgrade head
```

Запустите каждый процесс в отдельном терминале с тем же окружением:

```bash
uvicorn app.main:app --reload --port 8000
celery -A app.tasks.celery_app worker -l info -c 4
celery -A app.tasks.celery_app beat -l info
python -m app.bot.main
```

## Тесты

В активированном Python-окружении из каталога `priceradar`:

```bash
TESTING=1 python -m pytest tests/ -v
```

Тестовый режим использует синтетическую конфигурацию; проверки сервисов работают с SQLite в памяти. Он не заменяет проверку реальных маркетплейсов и платежей.

## Структура

```text
priceradar/
├── app/
│   ├── api/          HTTP API и дашборд
│   ├── bot/          Telegram-бот
│   ├── parsers/      парсеры маркетплейсов
│   ├── tasks/        задачи Celery и расписание
│   ├── services/     цены, уведомления и подписки
│   ├── models/       модели SQLAlchemy
│   ├── schemas/      схемы API
│   ├── templates/    веб-страницы
│   └── static/       стили
├── alembic/          миграции БД
├── tests/            парсеры и сервисы
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## English

PriceRadar is an MVP for marketplace price monitoring with a Telegram bot, price-history dashboard, configurable alerts, and subscription tiers. It uses FastAPI, PostgreSQL, Redis, Celery, aiogram, and Docker Compose.

Clone the repository, enter `priceradar`, copy `.env.example`, and replace its placeholder credentials. Start `db` and `redis`, apply Alembic migrations, then start all Compose services using the commands above. The dashboard requires authentication. Unit tests run with `TESTING=1 python -m pytest tests/ -v`.

Plan intervals are configuration values: the current scheduler runs every 30 minutes, including the Pro tier. Marketplace parsers and public deployment need separate validation.

