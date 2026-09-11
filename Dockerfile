FROM python:3.12-slim

# Create a non-root user
RUN useradd \
    --create-home \
    --shell /usr/sbin/nologin \
    appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]