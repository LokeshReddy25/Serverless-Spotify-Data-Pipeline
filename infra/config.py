"""Names and settings shared by the deploy and teardown scripts."""
import os
import re

import boto3

BUCKET_ENV_VAR = "SPOTIFY_PIPELINE_BUCKET"

EXTRACT_FUNCTION = "SpotifyExtractData"
TRANSFORM_FUNCTION = "SpotifyTransformData"
SCHEDULE_RULE = "SpotifyDailyExtractionRule"
DEFAULT_SCHEDULE = "cron(0 12 * * ? *)"  # daily, 12:00 UTC
GLUE_DATABASE = "spotify_db"
GLUE_CRAWLER = "spotify_data_crawler"

RAW_PREFIX = "raw_data/to_process/"
TRANSFORMED_PREFIX = "transformed_data/"

# AWS-managed "AWS SDK for pandas" layer. Override with --pandas-layer-arn or PANDAS_LAYER_ARN
# if this version is not published in your region.
PANDAS_LAYER_ENV_VAR = "PANDAS_LAYER_ARN"
PANDAS_LAYER_TEMPLATE = "arn:aws:lambda:{region}:336392948345:layer:AWSSDKPandas-Python310:14"

# S3 general-purpose bucket naming rules (simplified): 3-63 chars, lowercase letters, digits,
# dots and hyphens, starting and ending with a letter or digit, no "..", not an IP address.
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_IP_RE = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def resolve_bucket_name(cli_value=None):
    """Return the fixed pipeline bucket name from --bucket-name or SPOTIFY_PIPELINE_BUCKET."""
    name = (cli_value or os.environ.get(BUCKET_ENV_VAR, "")).strip()
    if not name:
        raise SystemExit(f"ERROR: no bucket name given. Pass --bucket-name or set {BUCKET_ENV_VAR}.")
    if not _BUCKET_NAME_RE.match(name) or ".." in name or _IP_RE.match(name):
        raise SystemExit(f"ERROR: '{name}' is not a valid S3 bucket name (3-63 characters: lowercase "
                         "letters, digits, '.' and '-', starting and ending with a letter or digit).")
    return name


def get_session(region=None):
    """boto3 session from the standard credential chain; fails clearly if no region is set."""
    session = boto3.Session(region_name=region) if region else boto3.Session()
    if not session.region_name:
        raise SystemExit("ERROR: no AWS region configured. Set AWS_REGION / AWS_DEFAULT_REGION, "
                         "or use a profile that has a region.")
    return session


def pandas_layer_arn(region, override=None):
    return override or os.environ.get(PANDAS_LAYER_ENV_VAR) or PANDAS_LAYER_TEMPLATE.format(region=region)
