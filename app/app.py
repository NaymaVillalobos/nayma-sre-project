import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram
from prometheus_client import generate_latest


APP_VERSION = "1.0.0"

DB_PATH = os.getenv(
    "DATABASE_PATH",
    "/tmp/nayma_appointments.db",
)

ALLOWED_SERVICES = {
    "consultation",
    "technical-support",
    "account-review",
}

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

APPOINTMENTS_CREATED = Counter(
    "appointments_created_total",
    "Total appointment creation attempts",
    ["service_type", "result"],
)

APPOINTMENTS_CANCELLED = Counter(
    "appointments_cancelled_total",
    "Total cancelled appointments",
)

APPLICATION_INFO = Gauge(
    "nayma_application_info",
    "Application information",
    ["service", "version"],
)

APPLICATION_INFO.labels(
    service="nayma-booking-api",
    version=APP_VERSION,
).set(1)


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                service_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def valid_email(email):
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(pattern, email))


def error_response(code, message, status):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                }
            }
        ),
        status,
    )


def create_app():
    app = Flask(__name__)
    init_db()

    @app.before_request
    def start_timer():
        request.start_time = time.perf_counter()

    @app.after_request
    def record_metrics(response):
        duration = time.perf_counter() - request.start_time

        endpoint = (
            request.url_rule.rule
            if request.url_rule
            else "unknown"
        )

        REQUEST_COUNT.labels(
            request.method,
            endpoint,
            str(response.status_code),
        ).inc()

        REQUEST_DURATION.labels(
            request.method,
            endpoint,
        ).observe(duration)

        response.headers["X-Request-ID"] = (
            request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )

        return response

    @app.route("/")
    def index():
        return jsonify(
            {
                "service": "nayma-booking-api",
                "project": "Nayma SRE Project",
                "version": APP_VERSION,
            }
        )

    @app.route("/health")
    def health():
        return jsonify(
            {
                "status": "healthy",
                "service": "nayma-booking-api",
                "version": APP_VERSION,
            }
        )

    @app.route("/ready")
    def ready():
        try:
            with get_db() as connection:
                connection.execute("SELECT 1").fetchone()
                connection.execute(
                    "SELECT id FROM appointments LIMIT 1"
                ).fetchone()

            return jsonify({"status": "ready"}), 200

        except sqlite3.Error:
            return jsonify({"status": "not-ready"}), 503

    @app.route("/appointments", methods=["GET"])
    def appointments():
        with get_db() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM appointments
                ORDER BY created_at DESC
                """
            ).fetchall()

        return jsonify([dict(row) for row in rows])

    @app.route("/appointments", methods=["POST"])
    def create_appointment():
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return error_response(
                "VALIDATION_ERROR",
                "A JSON request body is required.",
                400,
            )

        required_fields = [
            "customer_name",
            "customer_email",
            "appointment_date",
            "service_type",
        ]

        for field in required_fields:
            if not data.get(field):
                return error_response(
                    "VALIDATION_ERROR",
                    f"Missing required field: {field}",
                    400,
                )

        if not valid_email(data["customer_email"]):
            return error_response(
                "VALIDATION_ERROR",
                "Invalid email address.",
                400,
            )

        if data["service_type"] not in ALLOWED_SERVICES:
            return error_response(
                "VALIDATION_ERROR",
                "Invalid service type.",
                400,
            )

        try:
            appointment_date = datetime.fromisoformat(
                data["appointment_date"].replace(
                    "Z",
                    "+00:00",
                )
            )

            if appointment_date.tzinfo is None:
                appointment_date = appointment_date.replace(
                    tzinfo=timezone.utc
                )

            appointment_date = appointment_date.astimezone(
                timezone.utc
            )

            if appointment_date <= datetime.now(timezone.utc):
                return error_response(
                    "VALIDATION_ERROR",
                    "Appointment date must be in the future.",
                    400,
                )

        except (ValueError, AttributeError):
            return error_response(
                "VALIDATION_ERROR",
                "Appointment date must use ISO 8601 format.",
                400,
            )

        appointment = {
            "id": str(uuid.uuid4()),
            "customer_name": data["customer_name"],
            "customer_email": data["customer_email"],
            "appointment_date": appointment_date.isoformat(),
            "service_type": data["service_type"],
            "status": "confirmed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with get_db() as connection:
                connection.execute(
                    """
                    INSERT INTO appointments (
                        id,
                        customer_name,
                        customer_email,
                        appointment_date,
                        service_type,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        appointment["id"],
                        appointment["customer_name"],
                        appointment["customer_email"],
                        appointment["appointment_date"],
                        appointment["service_type"],
                        appointment["status"],
                        appointment["created_at"],
                    ),
                )

            APPOINTMENTS_CREATED.labels(
                data["service_type"],
                "success",
            ).inc()

        except sqlite3.Error:
            APPOINTMENTS_CREATED.labels(
                data["service_type"],
                "failure",
            ).inc()

            return error_response(
                "DATABASE_ERROR",
                "Unable to create appointment.",
                500,
            )

        return jsonify(appointment), 201

    @app.route("/appointments/<appointment_id>")
    def get_appointment(appointment_id):
        with get_db() as connection:
            row = connection.execute(
                "SELECT * FROM appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()

        if not row:
            return error_response(
                "NOT_FOUND",
                "Appointment not found.",
                404,
            )

        return jsonify(dict(row))

    @app.route(
        "/appointments/<appointment_id>",
        methods=["DELETE"],
    )
    def cancel_appointment(appointment_id):
        with get_db() as connection:
            row = connection.execute(
                "SELECT * FROM appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()

            if not row:
                return error_response(
                    "NOT_FOUND",
                    "Appointment not found.",
                    404,
                )

            if row["status"] != "cancelled":
                connection.execute(
                    """
                    UPDATE appointments
                    SET status = 'cancelled'
                    WHERE id = ?
                    """,
                    (appointment_id,),
                )

                APPOINTMENTS_CANCELLED.inc()

        return jsonify(
            {
                "id": appointment_id,
                "status": "cancelled",
            }
        )

    @app.route("/metrics")
    def metrics():
        return (
            generate_latest(),
            200,
            {"Content-Type": CONTENT_TYPE_LATEST},
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )
