FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DATABASE_PATH=/tmp/nayma_appointments.db

WORKDIR /app

RUN addgroup --system sre && \
    adduser --system --ingroup sre sre

COPY app/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

RUN chown -R sre:sre /app

USER sre

EXPOSE 8080

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "2", \
     "app.app:app"]
     