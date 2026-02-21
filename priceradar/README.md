# PriceRadar

Мониторинг цен на Wildberries, Ozon и Яндекс Маркете с алертами в Telegram.

## Что умеет

- Парсит цены на WB, Ozon и Яндекс Маркете
- Telegram-бот для добавления товаров и настройки алертов
- Веб-дашборд с графиками
- Алерты: снижение/повышение цены, целевая цена, возврат в наличие
- Тарифы: Free / Basic / Pro

## Стек

Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL, Redis, Celery, aiogram 3, Jinja2 + HTMX, httpx, Docker Compose

## Запуск

```bash
cp .env.example .env
# заполнить .env (токен бота, БД, etc.)

docker compose up -d --build
docker compose exec app alembic upgrade head
```

Дашборд: http://localhost:8000/dashboard
Бот: /start в Telegram

## Без Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

uvicorn app.main:app --reload --port 8000
celery -A app.tasks.celery_app worker -l info -c 4
celery -A app.tasks.celery_app beat -l info
python -m app.bot.main
```

## Тесты

```bash
pytest tests/ -v
```

## Структура

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

## Тарифы

| | Free | Basic (990 руб/мес) | Pro (2490 руб/мес) |
|---|---|---|---|
| Товаров | 5 | 50 | 200 |
| Обновление | 2 ч | 30 мин | 15 мин |
| Маркетплейсы | 1 | 3 | 3 |
| История | 7 дн | 30 дн | 90 дн |
| Алерты | 3 | 20 | unlim |

## Прокси

```
PROXY_LIST=http://user1:pass@proxy1:8080,http://user2:pass@proxy2:8080
```
