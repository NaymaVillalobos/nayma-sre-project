def test_home(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["project"] == "Nayma SRE Project"


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json["status"] == "healthy"
    assert response.json["service"] == "nayma-booking-api"
    assert response.json["version"] == "1.0.0"


def test_ready(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json["status"] == "ready"


def test_metrics(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"http_requests_total" in response.data
    assert b"http_request_duration_seconds" in response.data
