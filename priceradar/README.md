# PriceRadar

Сервис мониторинга цен на маркетплейсах (Wildberries, Ozon, Яндекс Маркет).

Отслеживает изменения цен на товары конкурентов и присылает алерты в Telegram.

## Возможности

- **Отслеживание цен** на Wildberries, Ozon и Яндекс Маркете
- **Telegram-бот** для управления товарами и алертами
- **Веб-дашборд** с графиками цен (Chart.js)
- **Гибкие алерты**: снижение/повышение цены, целевая цена, возврат в наличие
- **Подписочная модель**: Free / Basic / Pro
- **Автоматический парсинг** с настраиваемой частотой по тарифу

## Технический стек

- Python 3.12, FastAPI, SQLAlchemy 2.0 (async)
- PostgreSQL 16, Redis 7
- Celery (workers + beat)
- aiogram 3.x (Telegram-бот)
- Jinja2 + HTMX (веб-дашборд)
- httpx + selectolax (парсинг)
- Docker Compose

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone <repo-url>
cd priceradar
```

### 2. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите:

- `TELEGRAM_BOT_TOKEN` — токен бота от [@BotFather](https://t.me/BotFather)
- `TELEGRAM_BOT_USERNAME` — username бота (без @)
- `DB_PASSWORD` — пароль для PostgreSQL
- `SECRET_KEY` — секретный ключ приложения
- `YUKASSA_SHOP_ID` / `YUKASSA_SECRET_KEY` — данные ЮKassa (для оплаты подписок)

### 3. Запустить через Docker Compose

```bash
docker compose up -d --build
```

Это запустит:

| Сервис | Описание |
|--------|----------|
| `db` | PostgreSQL 16 |
| `redis` | Redis 7 |
| `app` | FastAPI (порт 8000) |
| `celery-worker` | Celery worker (4 конкурентных процесса) |
| `celery-beat` | Celery beat (планировщик) |
| `bot` | Telegram-бот |

### 4. Применить миграции

```bash
docker compose exec app alembic upgrade head
```

### 5. Проверить работу

- Веб-дашборд: http://localhost:8000/dashboard
- API документация (debug mode): http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Telegram-бот: найдите бота по username и отправьте `/start`

## Разработка

### Локальный запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Запустить PostgreSQL и Redis локально
# Обновить DATABASE_URL и REDIS_URL в .env

# Миграции
alembic upgrade head

# Веб-приложение
uvicorn app.main:app --reload --port 8000

# Celery worker (в отдельном терминале)
celery -A app.tasks.celery_app worker -l info -c 4

# Celery beat (в отдельном терминале)
celery -A app.tasks.celery_app beat -l info

# Telegram-бот (в отдельном терминале)
python -m app.bot.main
```

### Запуск тестов

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Структура проекта

```
priceradar/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # Настройки из .env
│   ├── database.py          # SQLAlchemy async engine
│   ├── models/              # SQLAlchemy модели
│   ├── schemas/             # Pydantic схемы
│   ├── api/                 # REST API + дашборд
│   ├── parsers/             # Парсеры маркетплейсов
│   ├── tasks/               # Celery задачи
│   ├── bot/                 # Telegram-бот (aiogram)
│   ├── services/            # Бизнес-логика
│   ├── templates/           # Jinja2 шаблоны
│   └── static/              # CSS
├── alembic/                 # Миграции БД
├── tests/                   # Тесты
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Тарифы

| | Free | Basic (990 руб/мес) | Pro (2490 руб/мес) |
|---|---|---|---|
| Товаров | 5 | 50 | 200 |
| Частота обновления | 2 часа | 30 мин | 15 мин |
| Маркетплейсы | 1 | 3 | 3 |
| История цен | 7 дней | 30 дней | 90 дней |
| Алерты | 3 | 20 | без лимита |
| Экспорт CSV | нет | да | да |

## Прокси

Для стабильной работы парсеров рекомендуется использовать прокси. Укажите список в `.env`:

```
PROXY_LIST=http://user1:pass@proxy1:8080,http://user2:pass@proxy2:8080
```

## Лицензия

MIT
