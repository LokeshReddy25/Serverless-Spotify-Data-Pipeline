"""Names and settings shared by the deploy and teardown scripts."""
import os
import re

import boto3

from infra import lambda_layers

BUCKET_ENV_VAR = "SPOTIFY_PIPELINE_BUCKET"

EXTRACT_FUNCTION = "SpotifyExtractData"
TRANSFORM_FUNCTION = "SpotifyTransformData"
SCHEDULE_RULE = "SpotifyDailyExtractionRule"
DEFAULT_SCHEDULE = "cron(0 12 * * ? *)"  # daily, 12:00 UTC
GLUE_DATABASE = "spotify_db"
GLUE_CRAWLER = "spotify_data_crawler"
ATHENA_WORKGROUP = "spotify_workgroup"
# Safety limit per Athena query in this workgroup (1 GiB). Queries that would scan more are cancelled.
ATHENA_BYTES_SCANNED_CUTOFF = 1024 ** 3

RAW_PREFIX = "raw_data/to_process/"
TRANSFORMED_PREFIX = "transformed_data/"
ATHENA_RESULTS_PREFIX = "athena_results/"

# Lambda runtime for both functions. Must match the Python version of the pandas layer below.
LAMBDA_RUNTIME = "python3.14"

# AWS-managed "AWS SDK for pandas" layer for the transform Lambda. The documented ARN for each
# region is in infra/lambda_layers.py (generated from the official layer list; the account ID and
# layer version differ by region). Override with --pandas-layer-arn or PANDAS_LAYER_ARN.
PANDAS_LAYER_ENV_VAR = "PANDAS_LAYER_ARN"

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


_LAYER_ARN_RE = re.compile(r"^arn:aws[a-z-]*:lambda:(?P<region>[a-z0-9-]+):\d{12}:layer:(?P<name>[A-Za-z0-9_-]+):\d+$")


def pandas_layer_arn(region, override=None):
    """Return the AWS SDK for pandas layer ARN to attach in `region`.

    Order: --pandas-layer-arn, then $PANDAS_LAYER_ARN, then the documented ARN for the region in
    infra/lambda_layers.py. Never builds an ARN from a template. Fails clearly if no ARN is known,
    if the ARN is for another region, or if it is an AWSSDKPandas layer for another Python version.
    """
    arn = (override or os.environ.get(PANDAS_LAYER_ENV_VAR, "")).strip()
    if not arn:
        arn = lambda_layers.LAYER_ARNS.get(region, "")
        if not arn:
            raise SystemExit(
                f"ERROR: no documented AWS SDK for pandas {lambda_layers.AWSSDKPANDAS_RELEASE} layer for "
                f"Python {lambda_layers.PYTHON_VERSION} in region '{region}'. Look it up at "
                f"{lambda_layers.DOCS_URL} and pass it with --pandas-layer-arn or {PANDAS_LAYER_ENV_VAR}.")

    match = _LAYER_ARN_RE.match(arn)
    if not match:
        raise SystemExit(f"ERROR: '{arn}' is not a Lambda layer version ARN.")
    if match.group("region") != region:
        raise SystemExit(f"ERROR: layer ARN is for region '{match.group('region')}', but the deployment region "
                         f"is '{region}'. Lambda layers must be in the same region as the function.")
    expected_name = f"AWSSDKPandas-Python{LAMBDA_RUNTIME.removeprefix('python').replace('.', '')}"
    name = match.group("name")
    if name.startswith("AWSSDKPandas-Python") and name != expected_name:
        raise SystemExit(f"ERROR: layer '{name}' does not match the {LAMBDA_RUNTIME} runtime "
                         f"(expected {expected_name}).")
    return arn
