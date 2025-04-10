#!/usr/bin/env python3
import subprocess
from airflow import DAG
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.utils.dates import days_ago
from airflow.utils.trigger_rule import TriggerRule
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.operators.bash import BashOperator
from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
from airflow.exceptions import AirflowFailException
from datetime import timedelta
from pathlib import Path
import boto3
import os
import great_expectations as ge
import re

SLACK_WEBHOOK_CONN_ID = "slack_default"
SLACK_CHANNEL = "#alert"
SLACK_USERNAME = "airflow-bot"


def send_slack_notification(context, status):
    safe_status = re.sub(r'[^a-zA-Z0-9._-]', '_', status)
    task_id = f"notify_slack_{context['task_instance'].task_id}_{safe_status}"

    msg = f":airflow: Task *{context['task_instance'].task_id}* in DAG *{context['dag'].dag_id}* {status}."
    return SlackWebhookOperator(
        task_id=task_id,
        slack_webhook_conn_id=SLACK_WEBHOOK_CONN_ID,
        message=msg,
        channel=SLACK_CHANNEL,
        username=SLACK_USERNAME
    ).execute(context=context)


def task_failure_callback(context):
    send_slack_notification(context, "failed ❌")


def run_all_gx_scripts():
    ARCHIVE_FOLDER = "/usr/local/airflow/include"
    gx_files = list(Path(ARCHIVE_FOLDER).glob("*.py"))
    if not gx_files:
        raise AirflowFailException(f"No GX files found in {ARCHIVE_FOLDER}!")

    failed_files = []  

    for file in gx_files:
        print(f"📈 Running GX validation script: {file.name}")
        try:
            result = subprocess.run(
                ["python3", str(file)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            print(f"✅ Output for {file.name}:\n{result.stdout}")

        except subprocess.CalledProcessError as e:
            print(f"❌ Error in {file.name}:\n{e.stderr}")
            failed_files.append(file.name)
            
            SlackWebhookOperator(
                task_id=f"alert_failure_{file.stem}",
                slack_webhook_conn_id=SLACK_WEBHOOK_CONN_ID,
                message=f":x: Validation failed for `{file.name}` in DAG run",
                username=SLACK_USERNAME,
                channel=SLACK_CHANNEL,
            ).execute(context={})

    if failed_files:
        print(f"⚠️ Some GX validations failed: {failed_files}")





def upload_validated_data_func(**kwargs):
    # Initialize S3 Hook
    s3_hook = S3Hook(aws_conn_id="aws_default")

    # Define local folder and S3 bucket/key prefix
    local_folder = Path("/usr/local/airflow/include/archive")
    bucket_name = "data-processed-eaae8e2e"
    s3_prefix = "processed/"

    # Check if local folder exists
    if not local_folder.exists():
        raise AirflowFailException(f"❌ Local folder does not exist: {local_folder}")

    # Find all CSV files in the local folder
    csv_files = list(local_folder.glob("*.csv"))
    if not csv_files:
        raise AirflowFailException(f"❌ No .csv files found to upload in {local_folder}")

    # Upload each CSV file to S3
    for file in csv_files:
        s3_key = f"{s3_prefix}{file.name}"
        print(f"📤 Uploading {file} to s3://{bucket_name}/{s3_key}")

        # Upload file using S3 Hook
        s3_hook.load_file(
            filename=str(file),
            key=s3_key,
            bucket_name=bucket_name,
            replace=True  
        )

    print(f"✅ Uploaded {len(csv_files)} CSV files successfully.")


def upload_data_docs_func(**kwargs):
    from pathlib import Path
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    from airflow.exceptions import AirflowFailException

    # Initialize S3 Hook
    s3_hook = S3Hook(aws_conn_id="aws_default")

    # Define local Data Docs path and S3 destination
    docs_path = Path("/usr/local/airflow/include/gx/uncommitted/data_docs/local_site/")
    bucket_name = "data-processed-eaae8e2e"

    if not docs_path.exists():
        raise AirflowFailException(f"❌ Data Docs path does not exist: {docs_path}")

    # Find all files recursively
    for file in docs_path.rglob("*"):
        if file.is_file():
            # Special case: move index.html to S3 root
            if file.name == "index.html":
                s3_key = "index.html"
            else:
                # Preserve relative path for all other files
                s3_key = str(file.relative_to(docs_path))

            print(f"📤 Uploading {file} to s3://{bucket_name}/{s3_key}")

            # Upload file
            s3_hook.load_file(
                filename=str(file),
                key=s3_key,
                bucket_name=bucket_name,
                replace=True
            )

    print(f"✅ Successfully uploaded Great Expectations Data Docs.")

default_args = {
    "owner": "data_team",
    "retries": 0,
    "sla": timedelta(minutes=10),
    "on_failure_callback": task_failure_callback,
}

with DAG(
    dag_id="etl_validate_upload_pipeline_v2",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["pyspark", "great_expectations", "s3"],
) as dag:

    start = DummyOperator(task_id="start")

    run_spark_etl = BashOperator(
        task_id="run_spark_etl",
        bash_command="python3 /usr/local/airflow/include/spark_jobs/ETL.py"
    )

    validate_all_gx_assets = PythonOperator(
        task_id="validate_all_gx_assets",
        python_callable=run_all_gx_scripts,
    )

    upload_validated_files = PythonOperator(
        task_id="upload_validated_data_to_s3",
        python_callable=upload_validated_data_func,   
    )

    upload_gx_report = PythonOperator(
        task_id="upload_great_expectations_docs",
        python_callable=upload_data_docs_func,       
    )

    end = DummyOperator(task_id="end")

    start >> run_spark_etl >> validate_all_gx_assets >> upload_validated_files >> upload_gx_report >> end

