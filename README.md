# Distributed Order Processing System

Распределенная система управления заказами, состоящая из двух микросервисов, взаимодействующих через RabbitMQ.

## Архитектура

Система состоит из двух автономных микросервисов:

### Order Service
- Принимает HTTP запросы на создание заказов
- Сохраняет заказы в PostgreSQL
- Публикует события `order.created` в RabbitMQ
- Подписывается на события `order.processed` для обновления статуса заказов
- Предоставляет API для получения статуса заказа

### Processor Service
- Подписывается на события `order.created`
- Выполняет обработку заказов (валидация, симуляция бизнес-логики)
- Сохраняет состояние обработки в своей БД (идемпотентность)
- Публикует события `order.processed` с результатом обработки

## Технологический стек

- **Python 3.12**
- **FastAPI** - веб-фреймворк
- **SQLAlchemy 2.0** - ORM с async поддержкой
- **Alembic** - миграции БД
- **PostgreSQL** - реляционная СУБД
- **RabbitMQ** - брокер сообщений
- **aio-pika** - асинхронный клиент RabbitMQ
- **Pydantic** - валидация данных
- **Docker & Docker Compose** - контейнеризация
- **pytest** - тестирование
- **uv** - менеджер пакетов

## Быстрый старт (Docker Compose)

### Требования
- Docker 20.10+
- Docker Compose 2.0+
- Git

### Запуск системы

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd <project-directory>
```

2. Запустите все сервисы через Docker Compose:
```bash
docker-compose up -d --build
```

3. Проверьте статус сервисов:
```bash
docker-compose ps
```

4. Просмотрите логи:
```bash
# Все сервисы
docker-compose logs -f

# Только order_service
docker-compose logs -f order_service

# Только processor_service
docker-compose logs -f processor_service
```

### Доступ к сервисам

Сервисы будут доступны по адресам:
- **Order Service API**: http://localhost:8000
- **Order Service Swagger**: http://localhost:8000/docs
- **Order Service ReDoc**: http://localhost:8000/redoc
- **Processor Service API**: http://localhost:8001
- **Processor Service Swagger**: http://localhost:8001/docs
- **Processor Service ReDoc**: http://localhost:8001/redoc
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)

### Остановка системы

```bash
# Остановить сервисы, но сохранить данные
docker-compose down

# Остановить сервисы и удалить тома с данными
docker-compose down -v
```

### API Endpoints

#### Order Service

**Создать заказ:**
```bash
POST http://localhost:8000/orders
Content-Type: application/json

{
  "customer_id": "customer-123",
  "items": [
    {
      "product_id": "product-1",
      "quantity": 2,
      "price": 10.50
    },
    {
      "product_id": "product-2",
      "quantity": 1,
      "price": 25.00
    }
  ]
}
```

**Получить статус заказа:**
```bash
GET http://localhost:8000/orders/{order_id}
```

**Health check:**
```bash
GET http://localhost:8000/health
GET http://localhost:8001/health
```

### Пример использования

```bash
# Создать заказ
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "customer-123",
    "items": [
      {"product_id": "product-1", "quantity": 2, "price": 10.50}
    ]
  }'

# Получить статус заказа (замените ORDER_ID на ID из предыдущего ответа)
curl http://localhost:8000/orders/ORDER_ID
```

## Запуск тестов

### Order Service
```bash
cd order_service
uv pip install -e ".[dev]"
pytest tests/ -v
```

### Processor Service
```bash
cd processor_service
uv pip install -e ".[dev]"
pytest tests/ -v
```

## Локальная разработка

### Order Service

1. Создайте виртуальное окружение:
```bash
cd order_service
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

4. Запустите сервис:
```bash
uvicorn app.main:app --reload --port 8000
```

### Processor Service

Аналогично Order Service, но с портом 8001.

## Обеспечение надежности

### Идемпотентность
- Processor Service проверяет наличие записи по `order_id` перед обработкой
- Повторная обработка одного и того же события не создает дубликатов

### Обработка ошибок
- Dead Letter Queue (DLQ) для сообщений, которые не удалось обработать
- Retry механизм с экспоненциальной задержкой
- Логирование всех ошибок в JSON формате

### Транзакционность
- Все операции с БД выполняются в транзакциях
- Публикация событий происходит после успешного сохранения в БД

### Мониторинг
- Health endpoints для проверки состояния сервисов
- Структурированное логирование (JSON)
- Метрики готовности сервисов

## Структура проекта

```
order-service/
├── app/
│   ├── api/          # HTTP endpoints
│   ├── core/         # Конфигурация, БД, брокер
│   ├── models/       # SQLAlchemy модели
│   ├── repositories/ # Слой доступа к данным
│   ├── schemas/      # Pydantic схемы
│   ├── services/     # Бизнес-логика
│   └── main.py       # Точка входа
├── alembic/          # Миграции БД
├── tests/            # Тесты
├── Dockerfile
├── pyproject.toml
└── .env.example

processor-service/
├── app/
│   ├── api/          # HTTP endpoints
│   ├── core/         # Конфигурация, БД, брокер
│   ├── models/       # SQLAlchemy модели
│   ├── repositories/ # Слой доступа к данным
│   ├── schemas/      # Pydantic схемы
│   ├── services/     # Бизнес-логика обработки
│   └── main.py       # Точка входа
├── alembic/          # Миграции БД
├── tests/            # Тесты
├── Dockerfile
├── pyproject.toml
└── .env.example
```