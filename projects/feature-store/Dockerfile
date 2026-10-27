FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY src ./src
COPY scripts ./scripts
RUN useradd --create-home app
USER app
EXPOSE 8001
CMD ["uvicorn", "serving.api:app", "--host", "0.0.0.0", "--port", "8001"]
