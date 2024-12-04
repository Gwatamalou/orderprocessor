# Архитектурное описание системы

## Обзор

Система представляет собой распределенную архитектуру из двух автономных микросервисов, взаимодействующих через брокер сообщений RabbitMQ. Каждый сервис имеет собственную базу данных PostgreSQL, что обеспечивает полную автономность и независимость развертывания.

## Архитектурные решения

### 1. Чистая архитектура (Clean Architecture)

Каждый сервис организован по принципам чистой архитектуры с четким разделением слоев:

```
app/
├── api/          # Presentation Layer - HTTP endpoints
├── services/     # Application Layer - бизнес-логика, оркестрация
├── repositories/ # Infrastructure Layer - доступ к данным
├── models/       # Domain Layer - доменные модели
├── schemas/      # DTO - объекты передачи данных
└── core/         # Infrastructure - конфигурация, БД, брокер
```

**Преимущества:**
- Доменная логика изолирована от инфраструктуры
- Легкость тестирования через dependency injection
- Возможность замены инфраструктурных компонентов без изменения бизнес-логики

### 2. Event-Driven Architecture

Взаимодействие между сервисами реализовано через асинхронный обмен событиями:

**Поток событий:**
```
Order Service → order.created → RabbitMQ → Processor Service
Processor Service → order.processed → RabbitMQ → Order Service
```

**Преимущества:**
- Слабая связанность сервисов
- Асинхронная обработка
- Возможность масштабирования независимо
- Устойчивость к временной недоступности сервисов

### 3. Database per Service

Каждый сервис имеет собственную базу данных:
- **Order Service**: `order_db` - хранит заказы и их статусы
- **Processor Service**: `processor_db` - хранит записи обработки

**Преимущества:**
- Полная автономность сервисов
- Независимое масштабирование БД
- Изоляция данных

**Недостатки:**
- Невозможность использовать транзакции БД между сервисами
- Необходимость обеспечения консистентности через SAGA

## Обеспечение надежности

### Идемпотентность

**Проблема:** При сбоях сети или перезапусках сервисов одно и то же событие может быть доставлено несколько раз.

**Решение в Processor Service:**
```python
async def process_order(self, event: OrderCreatedEvent) -> None:
    existing = await self.repository.get_by_order_id(event.order_id)

    if existing:
        logger.info(f"Order {event.order_id} already processed, skipping")
        return

    # Создаем запись с уникальным order_id
    record = ProcessingRecord(order_id=event.order_id, ...)
    await self.repository.create(record)
```

**Механизм:**
- Используется `order_id` как естественный идентификатор для дедупликации
- Проверка существования записи перед обработкой
- Уникальный индекс на `order_id` в БД предотвращает дубликаты на уровне БД

### Обработка ошибок и Dead Letter Queue

**Конфигурация очередей:**
```python
queue = await channel.declare_queue(
    "processor-service.order.created",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "orders.dlx",
        "x-dead-letter-routing-key": "order.created.failed"
    }
)
```

**Механизм:**
1. При ошибке обработки сообщение отклоняется (`requeue=False`)
2. RabbitMQ автоматически перенаправляет сообщение в DLX (Dead Letter Exchange)
3. Сообщение попадает в DLQ (Dead Letter Queue) для последующего анализа

**Преимущества:**
- Предотвращение бесконечных циклов обработки
- Сохранение проблемных сообщений для анализа
- Возможность ручной повторной обработки

### Транзакционность и консистентность

**Паттерн Transactional Outbox (упрощенная версия):**

В Order Service:
```python
async def create_order(self, order_data: OrderCreate) -> OrderResponse:
    # 1. Сохраняем заказ в БД (в транзакции)
    created_order = await self.repository.create(order)

    # 2. Публикуем событие после успешного commit
    await broker.publish("order.created", event.model_dump_json().encode())
```

**Гарантии:**
- Событие публикуется только после успешного сохранения в БД
- Если публикация не удалась, транзакция уже завершена, но можно реализовать retry

**Улучшения для production:**
- Сохранение событий в таблицу outbox в той же транзакции
- Отдельный процесс для чтения из outbox и публикации в брокер
- Гарантия at-least-once delivery

### SAGA Pattern

Система реализует упрощенный вариант SAGA паттерна для распределенных транзакций:

**Сценарий успешной обработки:**
```
1. Order Service: создает заказ (status=pending)
2. Order Service: публикует order.created
3. Processor Service: обрабатывает заказ
4. Processor Service: публикует order.processed (status=completed)
5. Order Service: обновляет статус заказа (status=completed)
```

**Сценарий с ошибкой:**
```
1. Order Service: создает заказ (status=pending)
2. Order Service: публикует order.created
3. Processor Service: обработка завершается с ошибкой
4. Processor Service: публикует order.processed (status=failed, error_message)
5. Order Service: обновляет статус заказа (status=failed)
```

**Состояния обработки в Processor Service:**
- `PENDING` - получено событие, запись создана
- `PROCESSING` - идет обработка
- `COMPLETED` - успешно обработано
- `FAILED` - ошибка обработки

## Технические детали

### Dependency Injection

Используется встроенный механизм FastAPI для инъекции зависимостей:

```python
def get_order_service(db: AsyncSession = Depends(get_db)) -> OrderService:
    repository = OrderRepository(db)
    return OrderService(repository)

@router.post("/orders")
async def create_order(
    order_data: OrderCreate,
    service: OrderService = Depends(get_order_service)
) -> OrderResponse:
    return await service.create_order(order_data)
```

**Преимущества:**
- Легкость тестирования (можно подменить зависимости)
- Управление жизненным циклом объектов
- Чистый и читаемый код

### Асинхронность

Все операции ввода-вывода выполняются асинхронно:
- **SQLAlchemy async** - асинхронные запросы к БД
- **aio-pika** - асинхронная работа с RabbitMQ
- **FastAPI** - асинхронные HTTP handlers

**Преимущества:**
- Высокая производительность при I/O операциях
- Эффективное использование ресурсов
- Возможность обработки множества запросов одновременно

### Логирование

Структурированное логирование в JSON формате:

```python
{
  "timestamp": "2024-12-04T17:30:45.123Z",
  "level": "INFO",
  "logger": "app.services.order",
  "message": "Order created: order-123"
}
```

**Преимущества:**
- Легкость парсинга и анализа логов
- Интеграция с системами мониторинга (ELK, Grafana Loki)
- Структурированный контекст для отладки

## Ограничения текущей реализации

1. **Отсутствие полноценного Outbox Pattern**
   - События публикуются сразу после commit БД
   - Риск потери события при сбое между commit и публикацией
   - **Решение:** Реализовать таблицу outbox и polling publisher

2. **Упрощенная обработка ошибок**
   - Нет автоматических retry с экспоненциальной задержкой
   - DLQ требует ручной обработки
   - **Решение:** Добавить retry механизм с backoff

3. **Отсутствие компенсирующих транзакций**
   - При ошибке заказ помечается как failed, но не откатывается
   - **Решение:** Реализовать compensating transactions для отмены операций

4. **Нет мониторинга и метрик**
   - Отсутствуют метрики производительности
   - Нет алертинга при ошибках
   - **Решение:** Интеграция с Prometheus, Grafana

5. **Отсутствие аутентификации и авторизации**
   - API открыт для всех
   - **Решение:** JWT токены, OAuth2

## Возможные улучшения

### Краткосрочные (1-2 недели)
1. Реализация Outbox Pattern для гарантированной доставки событий
2. Добавление retry механизма с экспоненциальной задержкой
3. Интеграция с Prometheus для метрик
4. Добавление correlation ID для трейсинга запросов

### Среднесрочные (1-2 месяца)
1. Реализация полноценного SAGA с компенсирующими транзакциями
2. Добавление Circuit Breaker паттерна
3. Интеграция с OpenTelemetry для distributed tracing
4. Реализация rate limiting и throttling

### Долгосрочные (3-6 месяцев)
1. Event Sourcing для полной истории изменений
2. CQRS для разделения чтения и записи
3. Kubernetes deployment с автомасштабированием
4. Multi-region deployment для высокой доступности

## Заключение

Архитектура системы обеспечивает:
- ✅ Слабую связанность сервисов через события
- ✅ Идемпотентность обработки событий
- ✅ Обработку ошибок через DLQ
- ✅ Чистую архитектуру с разделением слоев
- ✅ Асинхронную обработку для высокой производительности
- ✅ Автономность сервисов с собственными БД

Система готова к развертыванию и может быть расширена дополнительными паттернами надежности и масштабируемости по мере роста требований.
