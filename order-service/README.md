# Order Service

Микросервис управления заказами. Принимает HTTP запросы на создание заказов, сохраняет их в PostgreSQL и публикует события в RabbitMQ.

## Функциональность

- Создание заказов через REST API
- Получение статуса заказа
- Публикация событий `order.created` в RabbitMQ
- Обработка событий `order.processed` для обновления статуса
- Health check endpoint

## API Endpoints

### POST /orders
Создать новый заказ

**Request:**
```json
{
  "customer_id": "customer-123",
  "items": [
    {
      "product_id": "product-1",
      "quantity": 2,
      "price": 10.50
    }
  ]
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "customer_id": "customer-123",
  "items": [...],
  "total_amount": 21.0,
  "status": "pending",
  "error_message": null,
  "created_at": "2024-12-04T17:30:00Z",
  "updated_at": "2024-12-04T17:30:00Z"
}
```

### GET /orders/{order_id}
Получить статус заказа

**Response (200):**
```json
{
  "id": "uuid",
  "customer_id": "customer-123",
  "items": [...],
  "total_amount": 21.0,
  "status": "completed",
  "error_message": null,
  "created_at": "2024-12-04T17:30:00Z",
  "updated_at": "2024-12-04T17:30:15Z"
}
```

### GET /health
Health check

**Response (200):**
```json
{
  "status": "healthy"
}
```

## Локальная разработка

1. Создайте виртуальное окружение:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. Установите зависимости:
```bash
pip install uv
uv pip install -e ".[dev]"
```

3. Создайте `.env` файл:
```bash
cp .env.example .env
```

4. Запустите PostgreSQL и RabbitMQ (через Docker):
```bash
docker run -d -p 5432:5432 -e POSTGRES_USER=order_user -e POSTGRES_PASSWORD=order_pass -e POSTGRES_DB=order_db postgres:16
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3.13-management
```

5. Запустите сервис:
```bash
uvicorn app.main:app --reload --port 8000
```

## Тестирование

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

## Структура проекта

```
order-service/
├── app/
│   ├── api/
│   │   ├── orders.py      # Orders endpoints
│   │   └── health.py      # Health check
│   ├── core/
│   │   ├── config.py      # Конфигурация
│   │   ├── database.py    # SQLAlchemy setup
│   │   ├── broker.py      # RabbitMQ client
│   │   └── logging.py     # Логирование
│   ├── models/
│   │   └── order.py       # Order model
│   ├── repositories/
│   │   └── order.py       # Order repository
│   ├── schemas/
│   │   └── order.py       # Pydantic schemas
│   ├── services/
│   │   ├── order.py       # Бизнес-логика
│   │   └── consumer.py    # RabbitMQ consumer
│   └── main.py            # FastAPI app
├── alembic/               # Database migrations
├── tests/                 # Tests
├── Dockerfile
├── pyproject.toml
└── .env.example
```
