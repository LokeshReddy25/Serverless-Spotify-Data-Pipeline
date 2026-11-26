"""Lambda runtime and AWS SDK for pandas layer selection (no AWS calls)."""
import re

import pytest

from infra import config, lambda_layers, setup_lambda
from tools import generate_layer_arns

# Spot checks copied from https://aws-sdk-pandas.readthedocs.io/en/3.18.0/layers.html (read 2026-11-26).
DOC_SAMPLES = {
    "us-east-1": "arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python314:12",
    "ap-south-1": "arn:aws:lambda:ap-south-1:336392948345:layer:AWSSDKPandas-Python314:12",
    "af-south-1": "arn:aws:lambda:af-south-1:336392948345:layer:AWSSDKPandas-Python314:11",
    "ap-east-1": "arn:aws:lambda:ap-east-1:839552336658:layer:AWSSDKPandas-Python314:8",
    "ca-west-1": "arn:aws:lambda:ca-west-1:941713567376:layer:AWSSDKPandas-Python314:5",
    "cn-north-1": "arn:aws-cn:lambda:cn-north-1:406640652441:layer:AWSSDKPandas-Python314:7",
}


@pytest.fixture(autouse=True)
def no_layer_override(monkeypatch):
    monkeypatch.delenv(config.PANDAS_LAYER_ENV_VAR, raising=False)


def test_runtime_matches_the_layer_python_version():
    assert config.LAMBDA_RUNTIME == "python3.14"
    assert setup_lambda.RUNTIME == config.LAMBDA_RUNTIME
    assert lambda_layers.PYTHON_VERSION == "3.14"
    assert lambda_layers.AWSSDKPANDAS_RELEASE == "3.18.0"


@pytest.mark.parametrize("region,arn", sorted(DOC_SAMPLES.items()))
def test_documented_arn_is_used_for_the_region(region, arn):
    assert config.pandas_layer_arn(region) == arn


def test_layer_table_is_internally_consistent():
    assert len(lambda_layers.LAYER_ARNS) == 30
    for region, arn in lambda_layers.LAYER_ARNS.items():
        m = re.fullmatch(r"arn:(aws|aws-cn):lambda:([a-z0-9-]+):(\d{12}):layer:AWSSDKPandas-Python314:(\d+)", arn)
        assert m, arn
        assert m.group(2) == region
        assert (m.group(1) == "aws-cn") == region.startswith("cn-")


def test_unknown_region_fails_instead_of_guessing():
    with pytest.raises(SystemExit, match="no documented AWS SDK for pandas 3.18.0 layer for Python 3.14 "
                                         "in region 'us-gov-west-1'"):
        config.pandas_layer_arn("us-gov-west-1")


def test_env_var_overrides_the_table(monkeypatch):
    custom = "arn:aws:lambda:eu-west-1:111122223333:layer:my-pandas:3"
    monkeypatch.setenv(config.PANDAS_LAYER_ENV_VAR, custom)
    assert config.pandas_layer_arn("eu-west-1") == custom


def test_cli_override_beats_env_var(monkeypatch):
    monkeypatch.setenv(config.PANDAS_LAYER_ENV_VAR, "arn:aws:lambda:eu-west-1:111122223333:layer:from-env:1")
    cli = "arn:aws:lambda:eu-west-1:111122223333:layer:from-cli:2"
    assert config.pandas_layer_arn("eu-west-1", cli) == cli


def test_override_also_works_for_regions_missing_from_the_table():
    arn = "arn:aws-us-gov:lambda:us-gov-west-1:111122223333:layer:my-pandas:1"
    assert config.pandas_layer_arn("us-gov-west-1", arn) == arn


def test_layer_for_another_python_version_is_rejected():
    old = "arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python310:14"
    with pytest.raises(SystemExit, match="does not match the python3.14 runtime"):
        config.pandas_layer_arn("us-east-1", old)


def test_layer_from_another_region_is_rejected():
    with pytest.raises(SystemExit, match="layer ARN is for region 'us-west-2'"):
        config.pandas_layer_arn("us-east-1", DOC_SAMPLES["us-east-1"].replace("us-east-1", "us-west-2"))


@pytest.mark.parametrize("bad", ["not-an-arn", "arn:aws:lambda:us-east-1:336392948345:function:foo"])
def test_malformed_arn_is_rejected(bad):
    with pytest.raises(SystemExit, match="is not a Lambda layer version ARN"):
        config.pandas_layer_arn("us-east-1", bad)


def test_generator_keeps_only_x86_64_rows_for_the_requested_python():
    rst = """
+----------------+--------+-------+------------------------------------------------------------------+
| us-east-1      | 3.14   | x86_64| arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python314:12 |
| us-east-1      | 3.14   | arm64 | arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python314-Arm64:12 |
| us-east-1      | 3.13   | x86_64| arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python313:20 |
"""
    assert generate_layer_arns.parse(rst, "3.14") == {
        "us-east-1": "arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python314:12"}


def test_generator_rejects_an_arn_whose_region_does_not_match_its_row():
    rst = "| us-east-1 | 3.14 | x86_64| arn:aws:lambda:us-west-2:336392948345:layer:AWSSDKPandas-Python314:12 |"
    with pytest.raises(ValueError, match="unexpected ARN"):
        generate_layer_arns.parse(rst, "3.14")
