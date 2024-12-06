# Processor Service

Микросервис обработки заказов. Подписывается на события `order.created`, выполняет обработку и публикует результаты в RabbitMQ.

## Функциональность

- Подписка на события `order.created` из RabbitMQ
- Валидация и обработка заказов
- Сохранение состояния обработки в PostgreSQL (идемпотентность)
- Публикация событий `order.processed` с результатом
- Обработка ошибок через Dead Letter Queue
- Health check endpoint

## Логика обработки

1. Получение события `order.created`
2. Проверка идемпотентности (уже обработан?)
3. Создание записи обработки в БД
4. Валидация заказа:
   - Проверка суммы заказа
   - Проверка наличия товаров
   - Проверка количества и цен
   - Случайная симуляция ошибок (20% вероятность)
5. Публикация результата `order.processed`

## События

### Входящее: order.created
```json
{
  "order_id": "uuid",
  "customer_id": "customer-123",
  "items": [
    {
      "product_id": "product-1",
      "quantity": 2,
      "price": 10.50
    }
  ],
  "total_amount": 21.0,
  "created_at": "2024-12-04T17:30:00Z"
}
```

### Исходящее: order.processed
```json
{
  "order_id": "uuid",
  "status": "completed",
  "error_message": null
}
```

или при ошибке:

```json
{
  "order_id": "uuid",
  "status": "failed",
  "error_message": "Random validation failure"
}
```

## Идемпотентность

Сервис обеспечивает идемпотентность через:
1. Проверку существования записи по `order_id` перед обработкой
2. Уникальный индекс на `order_id` в БД
3. Повторная обработка того же события не создает дубликатов

```python
existing = await self.repository.get_by_order_id(event.order_id)
if existing:
    logger.info(f"Order {event.order_id} already processed, skipping")
    return
```

## Обработка ошибок

- При ошибке обработки сообщение отклоняется (`requeue=False`)
- RabbitMQ перенаправляет сообщение в Dead Letter Queue
- Статус записи обновляется на `failed` с сохранением ошибки
- Публикуется событие `order.processed` с информацией об ошибке

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
docker run -d -p 5433:5432 -e POSTGRES_USER=processor_user -e POSTGRES_PASSWORD=processor_pass -e POSTGRES_DB=processor_db postgres:16
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:3.13-management
```

5. Запустите сервис:
```bash
uvicorn app.main:app --reload --port 8001
```

## Тестирование

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html
```

## Структура проекта

```
processor-service/
├── app/
│   ├── api/
│   │   └── health.py         # Health check
│   ├── core/
│   │   ├── config.py         # Конфигурация
│   │   ├── database.py       # SQLAlchemy setup
│   │   ├── broker.py         # RabbitMQ client
│   │   └── logging.py        # Логирование
│   ├── models/
│   │   └── processing.py     # ProcessingRecord model
│   ├── repositories/
│   │   └── processing.py     # Processing repository
│   ├── schemas/
│   │   └── events.py         # Event schemas
│   ├── services/
│   │   ├── processor.py      # Бизнес-логика обработки
│   │   └── consumer.py       # RabbitMQ consumer
│   └── main.py               # FastAPI app
├── alembic/                  # Database migrations
├── tests/                    # Tests
├── Dockerfile
├── pyproject.toml
└── .env.example
```
