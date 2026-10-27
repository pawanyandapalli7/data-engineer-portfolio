FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src \
    MLFLOW_TRACKING_URI=sqlite:////models/mlflow.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
RUN useradd --create-home app && mkdir /models && chown app /models
USER app
# Run from /models so MLflow's ./mlruns artifact store lands on the shared volume.
WORKDIR /models
EXPOSE 8080
CMD ["uvicorn", "claims_model.serve:app", "--host", "0.0.0.0", "--port", "8080"]
