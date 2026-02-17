from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def dummy_task():
    print("Processing data...")

default_args = {
    "owner": "data-eng",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "sla": timedelta(minutes=30)
}

with DAG(
    dag_id="claims_pipeline_sla",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    default_args=default_args,
    catchup=False
) as dag:

    process_claims = PythonOperator(
        task_id="process_claims",
        python_callable=dummy_task
    )
