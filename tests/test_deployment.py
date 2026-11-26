"""deploy_all.py and infra/teardown.py, run end to end against moto (not real AWS)."""
import io
import os
import zipfile

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

import deploy_all
from infra import config, setup_glue_athena, setup_lambda, setup_s3, teardown
from infra.setup_iam_roles import ROLE_NAMES

BUCKET = "fixed-pipeline-bucket"
SECRET = "not-a-real-secret-value"


@pytest.fixture
def spotify_env(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "the-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setattr(setup_lambda, "ROLE_PROPAGATION_DELAY_S", 0)


def _empty_zip():
    buf = io.BytesIO()
    zipfile.ZipFile(buf, "w").close()
    return buf.getvalue()


@pytest.fixture
def fake_layer(aws, monkeypatch):
    """moto only accepts layers that exist in the mock, so publish a stand-in for the AWS-managed
    pandas layer and select it with the PANDAS_LAYER_ARN override."""
    arn = boto3.client("lambda").publish_layer_version(
        LayerName="AWSSDKPandas-stand-in", Content={"ZipFile": _empty_zip()})["LayerVersionArn"]
    monkeypatch.setenv(config.PANDAS_LAYER_ENV_VAR, arn)
    return arn


@pytest.fixture
def deployed(aws, spotify_env, fake_layer):
    deploy_all.main(["--bucket-name", BUCKET])
    return boto3.Session()


def _function_names(session):
    return sorted(f["FunctionName"] for f in session.client("lambda").list_functions()["Functions"])


def _role_names(session):
    return sorted(r["RoleName"] for r in session.client("iam").list_roles()["Roles"])


# ---------------------------------------------------------------- deploy

def test_deploy_creates_every_resource_with_the_fixed_bucket(deployed):
    s3, lam = deployed.client("s3"), deployed.client("lambda")
    assert [b["Name"] for b in s3.list_buckets()["Buckets"]] == [BUCKET]
    block = s3.get_public_access_block(Bucket=BUCKET)["PublicAccessBlockConfiguration"]
    assert all(block.values())

    assert _function_names(deployed) == sorted([config.EXTRACT_FUNCTION, config.TRANSFORM_FUNCTION])
    extract = lam.get_function_configuration(FunctionName=config.EXTRACT_FUNCTION)
    assert extract["Environment"]["Variables"]["S3_BUCKET_NAME"] == BUCKET
    assert extract["Role"].endswith("/SpotifyExtractLambdaRole")
    transform = lam.get_function_configuration(FunctionName=config.TRANSFORM_FUNCTION)
    assert transform["Environment"]["Variables"]["TRANSFORMED_S3_BUCKET"] == BUCKET
    assert [layer["Arn"] for layer in transform["Layers"]] == [os.environ[config.PANDAS_LAYER_ENV_VAR]]

    notif = s3.get_bucket_notification_configuration(Bucket=BUCKET)["LambdaFunctionConfigurations"]
    assert notif[0]["LambdaFunctionArn"].endswith(f":function:{config.TRANSFORM_FUNCTION}")
    rules = {r["Name"]: r["Value"] for r in notif[0]["Filter"]["Key"]["FilterRules"]}
    assert rules == {"prefix": config.RAW_PREFIX, "suffix": ".json"}

    events = deployed.client("events")
    assert events.describe_rule(Name=config.SCHEDULE_RULE)["ScheduleExpression"] == config.DEFAULT_SCHEDULE
    targets = events.list_targets_by_rule(Rule=config.SCHEDULE_RULE)["Targets"]
    assert targets[0]["Arn"].endswith(f":function:{config.EXTRACT_FUNCTION}")

    glue = deployed.client("glue")
    assert glue.get_database(Name=config.GLUE_DATABASE)["Database"]["Name"] == config.GLUE_DATABASE
    crawler = glue.get_crawler(Name=config.GLUE_CRAWLER)["Crawler"]
    assert crawler["Targets"]["S3Targets"][0]["Path"] == f"s3://{BUCKET}/transformed_data/"
    assert sorted(ROLE_NAMES) == _role_names(deployed)


class _GlueWithUpdateCrawler:
    """moto has not implemented glue.update_crawler; record the call instead of sending it."""

    def __init__(self, glue, calls):
        self._glue, self._calls = glue, calls

    def __getattr__(self, name):
        return getattr(self._glue, name)

    def update_crawler(self, **kwargs):
        self._calls.append(kwargs)


def test_deploy_is_repeatable(deployed, monkeypatch):
    calls = []
    real_setup_glue = setup_glue_athena.setup_glue
    monkeypatch.setattr(setup_glue_athena, "setup_glue",
                        lambda glue, iam, bucket: real_setup_glue(_GlueWithUpdateCrawler(glue, calls), iam, bucket))

    deploy_all.main(["--bucket-name", BUCKET])  # second run: updates in place, no new bucket

    assert [b["Name"] for b in deployed.client("s3").list_buckets()["Buckets"]] == [BUCKET]
    assert len(_function_names(deployed)) == 2
    assert [c["Name"] for c in calls] == [config.GLUE_CRAWLER]
    assert calls[0]["Targets"]["S3Targets"][0]["Path"] == f"s3://{BUCKET}/transformed_data/"


def test_bucket_name_can_come_from_env(aws, spotify_env, fake_layer, monkeypatch):
    monkeypatch.setenv(config.BUCKET_ENV_VAR, "bucket-from-env")
    deploy_all.main([])
    assert [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]] == ["bucket-from-env"]


def test_deploy_does_not_print_the_secret(aws, spotify_env, fake_layer, capsys):
    deploy_all.main(["--bucket-name", BUCKET])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err


def test_missing_bucket_name_fails_clearly(aws, spotify_env):
    with pytest.raises(SystemExit, match="--bucket-name or set SPOTIFY_PIPELINE_BUCKET"):
        deploy_all.main([])


@pytest.mark.parametrize("bad", ["UpperCase", "ab", "a..b", "192.168.0.1", "ends-with-", "under_score"])
def test_invalid_bucket_names_are_rejected(bad):
    with pytest.raises(SystemExit, match="not a valid S3 bucket name"):
        config.resolve_bucket_name(bad)


def test_default_pandas_layer_is_the_pinned_aws_managed_layer(monkeypatch):
    monkeypatch.delenv(config.PANDAS_LAYER_ENV_VAR, raising=False)
    expected = "arn:aws:lambda:eu-west-1:336392948345:layer:AWSSDKPandas-Python310:14"
    assert config.pandas_layer_arn("eu-west-1") == expected
    assert config.pandas_layer_arn("eu-west-1", "arn:custom") == "arn:custom"


def test_missing_region_fails_clearly(monkeypatch):
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(SystemExit, match="no AWS region configured"):
        config.get_session()


def test_bucket_owned_by_another_account_fails_clearly():
    s3 = boto3.client("s3", region_name="eu-west-1")
    with Stubber(s3) as stub:
        stub.add_client_error("create_bucket", service_error_code="BucketAlreadyExists", http_status_code=409)
        with pytest.raises(SystemExit, match="already used by another AWS account"):
            setup_s3.create_bucket(s3, "taken-name", "eu-west-1")


def test_existing_bucket_in_own_account_is_reused():
    s3 = boto3.client("s3", region_name="eu-west-1")
    with Stubber(s3) as stub:
        stub.add_client_error("create_bucket", service_error_code="BucketAlreadyOwnedByYou", http_status_code=409)
        stub.add_response("put_public_access_block", {})
        setup_s3.create_bucket(s3, "my-bucket", "eu-west-1")
        stub.assert_no_pending_responses()


def test_lambda_creation_retries_while_role_propagates(monkeypatch):
    monkeypatch.setattr(setup_lambda, "ROLE_PROPAGATION_DELAY_S", 0)
    lam = boto3.client("lambda", region_name="us-east-1")
    with Stubber(lam) as stub:
        stub.add_client_error("create_function", service_error_code="InvalidParameterValueException",
                              service_message="The role defined for the function cannot be assumed by Lambda.")
        stub.add_response("create_function", {"FunctionArn": "arn:aws:lambda:us-east-1:123:function:f"})
        arn = setup_lambda._create_function(lam, FunctionName="f", Role="r", Code={"ZipFile": b"x"})
    assert arn.endswith(":function:f")


def test_lambda_zip_contains_only_the_handler():
    data = setup_lambda.build_zip(setup_lambda.REPO_ROOT / "src" / "extract_lambda")
    assert zipfile.ZipFile(io.BytesIO(data)).namelist() == ["lambda_function.py"]


# ---------------------------------------------------------------- teardown

def test_teardown_dry_run_deletes_nothing(deployed, capsys):
    assert teardown.main(["--bucket-name", BUCKET]) == []
    assert "Dry run" in capsys.readouterr().out
    assert len(_function_names(deployed)) == 2


def test_teardown_removes_everything_deploy_created(deployed):
    s3, glue = deployed.client("s3"), deployed.client("glue")
    # Simulate pipeline activity: data files and a table made by the crawler.
    s3.put_object(Bucket=BUCKET, Key="raw_data/processed/a.json", Body=b"{}")
    s3.put_object(Bucket=BUCKET, Key="transformed_data/tracks/t.parquet", Body=b"x")
    glue.create_table(DatabaseName=config.GLUE_DATABASE, TableInput={"Name": "tracks"})
    deployed.client("logs").create_log_group(logGroupName=f"/aws/lambda/{config.EXTRACT_FUNCTION}")

    results = dict((label, status) for label, status in teardown.main(["--bucket-name", BUCKET, "--yes"]))

    assert set(results) == set(teardown.planned_resources(BUCKET)) - {
        f"Glue database {config.GLUE_DATABASE} (and its tables)",
        f"S3 bucket {BUCKET} (all objects and versions)"} | {
        f"Glue database {config.GLUE_DATABASE}", f"S3 bucket {BUCKET}"}
    assert results[f"CloudWatch log group /aws/lambda/{config.TRANSFORM_FUNCTION}"] == "not found"
    assert all(status == "deleted" for label, status in results.items() if "log group" not in label)

    assert s3.list_buckets()["Buckets"] == []
    assert _function_names(deployed) == []
    assert _role_names(deployed) == []
    assert deployed.client("events").list_rules()["Rules"] == []
    assert glue.get_crawlers()["Crawlers"] == []
    with pytest.raises(ClientError):
        glue.get_database(Name=config.GLUE_DATABASE)
    assert deployed.client("logs").describe_log_groups()["logGroups"] == []


def test_teardown_is_safe_to_rerun(deployed):
    teardown.main(["--bucket-name", BUCKET, "--yes"])
    results = teardown.main(["--bucket-name", BUCKET, "--yes"])
    assert {status for _, status in results} == {"not found"}


def test_teardown_refuses_bucket_owned_by_another_account():
    s3 = boto3.client("s3", region_name="us-east-1")
    with Stubber(s3) as stub:
        stub.add_client_error("head_bucket", service_error_code="403", http_status_code=403)
        with pytest.raises(SystemExit, match="not owned by account"):
            teardown._empty_and_delete_bucket(s3, "someone-elses-bucket", "123456789012")
