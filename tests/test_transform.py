import json

import awswrangler as wr
import pytest

from conftest import BUCKET, s3_event

RAW_KEY = "raw_data/to_process/spotify_top_50_2026-01-01_12-00-00.json"


@pytest.fixture
def raw_object(s3, sample_payload):
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=json.dumps(sample_payload))
    return RAW_KEY


def _keys(s3, prefix):
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])]


def test_transform_writes_three_parquet_tables(transform_module, s3, raw_object):
    result = transform_module.lambda_handler(s3_event(raw_object), None)

    assert result["statusCode"] == 200
    rows = {}
    for key in _keys(s3, "transformed_data/"):
        table = key.split("/")[1]
        rows[table] = len(wr.s3.read_parquet(f"s3://{BUCKET}/{key}"))
    # synthetic sample: 50 tracks, 40 unique albums, 35 unique artists
    assert rows == {"albums": 40, "artists": 35, "tracks": 50}


def test_transform_moves_raw_file_to_processed(transform_module, s3, raw_object):
    transform_module.lambda_handler(s3_event(raw_object), None)

    assert _keys(s3, "raw_data/to_process/") == []
    assert _keys(s3, "raw_data/processed/") == [RAW_KEY.replace("to_process/", "processed/")]


def test_transform_skips_keys_outside_raw_prefix(transform_module, s3):
    result = transform_module.lambda_handler(s3_event("somewhere_else/file.json"), None)

    assert result["statusCode"] == 200
    assert _keys(s3, "transformed_data/") == []


def test_transform_decodes_url_encoded_keys(transform_module, s3, sample_payload):
    key = "raw_data/to_process/spotify top 50.json"
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(sample_payload))

    result = transform_module.lambda_handler(s3_event("raw_data/to_process/spotify+top+50.json"), None)

    assert result["statusCode"] == 200
    assert len(_keys(s3, "transformed_data/")) == 3
