import pytest
import json
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_order_success(client: AsyncClient, mock_broker):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": 2, "price": 10.50},
            {"product_id": "product-2", "quantity": 1, "price": 25.00}
        ]
    })

    assert response.status_code == 201
    data = response.json()

    assert data["customer_id"] == "customer-123"
    assert data["total_amount"] == 46.0
    assert data["status"] == "pending"
    assert data["error_message"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert len(data["items"]) == 2

    assert len(mock_broker) == 1
    published = mock_broker[0]
    assert published["routing_key"] == "order.created"

    event_data = json.loads(published["message"].decode())
    assert event_data["order_id"] == data["id"]
    assert event_data["customer_id"] == "customer-123"
    assert event_data["total_amount"] == 46.0


@pytest.mark.asyncio
async def test_create_order_single_item(client: AsyncClient, mock_broker):
    response = await client.post("/orders", json={
        "customer_id": "customer-456",
        "items": [
            {"product_id": "product-1", "quantity": 5, "price": 7.99}
        ]
    })

    assert response.status_code == 201
    data = response.json()

    assert data["customer_id"] == "customer-456"
    assert data["total_amount"] == 39.95
    assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_create_order_invalid_empty_items(client: AsyncClient):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": []
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_invalid_negative_quantity(client: AsyncClient):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": -1, "price": 10.50}
        ]
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_invalid_zero_quantity(client: AsyncClient):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": 0, "price": 10.50}
        ]
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_invalid_negative_price(client: AsyncClient):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": 1, "price": -10.50}
        ]
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_invalid_zero_price(client: AsyncClient):
    response = await client.post("/orders", json={
        "customer_id": "customer-123",
        "items": [
            {"product_id": "product-1", "quantity": 1, "price": 0}
        ]
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_order_missing_customer_id(client: AsyncClient):
    response = await client.post("/orders", json={
        "items": [
            {"product_id": "product-1", "quantity": 1, "price": 10.50}
        ]
    })

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_order_success(client: AsyncClient, mock_broker):
    create_response = await client.post("/orders", json={
        "customer_id": "customer-789",
        "items": [
            {"product_id": "product-1", "quantity": 3, "price": 15.00}
        ]
    })

    assert create_response.status_code == 201
    order_id = create_response.json()["id"]

    get_response = await client.get(f"/orders/{order_id}")

    assert get_response.status_code == 200
    data = get_response.json()

    assert data["id"] == order_id
    assert data["customer_id"] == "customer-789"
    assert data["total_amount"] == 45.0
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_get_order_not_found(client: AsyncClient):
    response = await client.get("/orders/non-existent-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.asyncio
async def test_multiple_orders_different_customers(client: AsyncClient, mock_broker):
    response1 = await client.post("/orders", json={
        "customer_id": "customer-1",
        "items": [{"product_id": "product-1", "quantity": 1, "price": 10.00}]
    })

    response2 = await client.post("/orders", json={
        "customer_id": "customer-2",
        "items": [{"product_id": "product-2", "quantity": 2, "price": 20.00}]
    })

    assert response1.status_code == 201
    assert response2.status_code == 201

    order1 = response1.json()
    order2 = response2.json()

    assert order1["id"] != order2["id"]
    assert order1["customer_id"] == "customer-1"
    assert order2["customer_id"] == "customer-2"
    assert order1["total_amount"] == 10.0
    assert order2["total_amount"] == 40.0


@pytest.mark.asyncio
async def test_order_total_calculation(client: AsyncClient, mock_broker):
    response = await client.post("/orders", json={
        "customer_id": "customer-calc",
        "items": [
            {"product_id": "product-1", "quantity": 3, "price": 10.50},
            {"product_id": "product-2", "quantity": 2, "price": 15.75},
            {"product_id": "product-3", "quantity": 1, "price": 5.25}
        ]
    })

    assert response.status_code == 201
    data = response.json()

    expected_total = (3 * 10.50) + (2 * 15.75) + (1 * 5.25)
    assert data["total_amount"] == expected_total


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert "checks" in data
