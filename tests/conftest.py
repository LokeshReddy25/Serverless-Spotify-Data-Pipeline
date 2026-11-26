"""Shared pytest fixtures.

Every AWS call in these tests goes to moto's in-memory mock, never to real AWS.
The AWS_* values below are moto's documented placeholders, and the shared
credentials/config files point to empty temp paths so ~/.aws is never read.
"""
import importlib.util
import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REPO = Path(__file__).resolve().parent.parent
SAMPLE_FILE = REPO / "benchmarks" / "sample_data" / "synthetic_playlist_50.json"
BUCKET = "test-pipeline-bucket"
REGION = "us-east-1"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch, tmp_path):
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET",
                "SPOTIFY_PIPELINE_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no_credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no_config"))


@pytest.fixture
def aws():
    with mock_aws():
        yield


def load_handler(name):
    """Load src/<name>_lambda/lambda_function.py under a unique module name (both files share a name)."""
    path = REPO / "src" / f"{name}_lambda" / "lambda_function.py"
    spec = importlib.util.spec_from_file_location(f"{name}_lambda_function", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def s3(aws):
    client = boto3.client("s3", region_name=REGION)
    client.create_bucket(Bucket=BUCKET)
    return client


@pytest.fixture
def sample_payload():
    return json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def extract_module(aws):
    return load_handler("extract")


@pytest.fixture
def transform_module(aws):
    return load_handler("transform")


def s3_event(key, bucket=BUCKET):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
