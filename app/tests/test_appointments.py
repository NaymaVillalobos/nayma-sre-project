from datetime import UTC, datetime, timedelta


def valid_appointment():
    future = datetime.now(UTC) + timedelta(days=10)

    return {
        "customer_name": "SRE Test User",
        "customer_email": "sre-test@example.com",
        "appointment_date": future.isoformat(),
        "service_type": "consultation",
    }


def test_initially_empty(client):
    response = client.get("/appointments")

    assert response.status_code == 200
    assert response.json == []


def test_create_appointment(client):
    response = client.post(
        "/appointments",
        json=valid_appointment(),
    )

    assert response.status_code == 201
    assert response.json["status"] == "confirmed"
    assert response.json["service_type"] == "consultation"


def test_invalid_email(client):
    data = valid_appointment()
    data["customer_email"] = "invalid-email"

    response = client.post("/appointments", json=data)

    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"


def test_past_date(client):
    data = valid_appointment()

    data["appointment_date"] = (
        datetime.now(UTC) - timedelta(days=1)
    ).isoformat()

    response = client.post("/appointments", json=data)

    assert response.status_code == 400


def test_invalid_service(client):
    data = valid_appointment()
    data["service_type"] = "unknown"

    response = client.post("/appointments", json=data)

    assert response.status_code == 400


def test_get_and_cancel_appointment(client):
    created = client.post(
        "/appointments",
        json=valid_appointment(),
    )

    assert created.status_code == 201

    appointment_id = created.json["id"]

    response = client.get(
        f"/appointments/{appointment_id}"
    )

    assert response.status_code == 200
    assert response.json["id"] == appointment_id

    cancelled = client.delete(
        f"/appointments/{appointment_id}"
    )

    assert cancelled.status_code == 200
    assert cancelled.json["status"] == "cancelled"

    cancelled_again = client.delete(
        f"/appointments/{appointment_id}"
    )

    assert cancelled_again.status_code == 200
    assert cancelled_again.json["status"] == "cancelled"


def test_appointment_not_found(client):
    response = client.get("/appointments/not-real")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"


def test_cancel_appointment_not_found(client):
    response = client.delete("/appointments/not-real")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"
