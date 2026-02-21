# PriceRadar

🇷🇺 [Русский](#русский) | 🇬🇧 [English](#english)

---

## Русский

Мониторинг цен на Wildberries, Ozon и Яндекс Маркете с алертами в Telegram.

### Что умеет

- Парсит цены на WB, Ozon и Яндекс Маркете
- Telegram-бот для добавления товаров и настройки алертов
- Веб-дашборд с графиками
- Алерты: снижение/повышение цены, целевая цена, возврат в наличие
- Тарифы: Free / Basic / Pro

### Стек

Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, Celery, aiogram 3, Jinja2 + HTMX, httpx, Docker Compose

### Запуск

```bash
cd priceradar
cp .env.example .env
# заполнить .env (токен бота, БД, etc.)

docker compose up -d --build
docker compose exec app alembic upgrade head
```

Дашборд: http://localhost:8000/dashboard
Бот: /start в Telegram

### Без Docker

```bash
cd priceradar
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

uvicorn app.main:app --reload --port 8000
celery -A app.tasks.celery_app worker -l info -c 4
celery -A app.tasks.celery_app beat -l info
python -m app.bot.main
```

### Тесты

```bash
cd priceradar
pytest tests/ -v
```

### Структура

```
priceradar/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── schemas/
│   ├── api/
│   ├── parsers/
│   ├── tasks/
│   ├── bot/
│   ├── services/
│   ├── templates/
│   └── static/
├── alembic/
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Тарифы

| | Free | Basic (990 руб/мес) | Pro (2490 руб/мес) |
|---|---|---|---|
| Товаров | 5 | 50 | 200 |
| Обновление | 2 ч | 30 мин | 15 мин |
| Маркетплейсы | 1 | 3 | 3 |
| История | 7 дн | 30 дн | 90 дн |
| Алерты | 3 | 20 | unlim |

### Прокси

```
PROXY_LIST=http://user1:pass@proxy1:8080,http://user2:pass@proxy2:8080
```

---

## English

Price monitoring for Wildberries, Ozon, and Yandex Market with Telegram alerts.

### Features

- Parses prices on WB, Ozon, and Yandex Market
- Telegram bot for adding products and configuring alerts
- Web dashboard with charts
- Alerts: price drop/increase, target price, back in stock
- Plans: Free / Basic / Pro

### Tech Stack

Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, Celery, aiogram 3, Jinja2 + HTMX, httpx, Docker Compose

### Getting Started

```bash
cd priceradar
cp .env.example .env
# fill in .env (bot token, DB, etc.)

docker compose up -d --build
docker compose exec app alembic upgrade head
```

Dashboard: http://localhost:8000/dashboard
Bot: /start in Telegram

### Without Docker

```bash
cd priceradar
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

uvicorn app.main:app --reload --port 8000
celery -A app.tasks.celery_app worker -l info -c 4
celery -A app.tasks.celery_app beat -l info
python -m app.bot.main
```

### Tests

```bash
cd priceradar
pytest tests/ -v
```

### Project Structure

```
priceradar/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/
│   ├── schemas/
│   ├── api/
│   ├── parsers/
│   ├── tasks/
│   ├── bot/
│   ├── services/
│   ├── templates/
│   └── static/
├── alembic/
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### Plans

| | Free | Basic ($10/mo) | Pro ($25/mo) |
|---|---|---|---|
| Products | 5 | 50 | 200 |
| Update interval | 2 h | 30 min | 15 min |
| Marketplaces | 1 | 3 | 3 |
| History | 7 days | 30 days | 90 days |
| Alerts | 3 | 20 | unlim |

### Proxy

```
PROXY_LIST=http://user1:pass@proxy1:8080,http://user2:pass@proxy2:8080
```
