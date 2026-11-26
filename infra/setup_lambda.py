"""Package and deploy both Lambda functions and wire the S3 trigger for the transform Lambda.

Usage: python -m infra.setup_lambda --bucket-name NAME [--pandas-layer-arn ARN]
Spotify credentials come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET or a hidden prompt.
"""
import argparse
import io
import os
import time
import zipfile
from pathlib import Path

from botocore.exceptions import ClientError

from infra import config
from infra.setup_iam_roles import EXTRACT_ROLE, TRANSFORM_ROLE
from infra.spotify_credentials import get_spotify_credentials

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME = config.LAMBDA_RUNTIME
HANDLER = "lambda_function.lambda_handler"
# A newly created IAM role can take a few seconds before Lambda is allowed to assume it.
ROLE_PROPAGATION_RETRIES = 6
ROLE_PROPAGATION_DELAY_S = 5


def build_zip(source_dir):
    """Zip the .py files of a Lambda source folder in memory (nothing is written to disk)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(source_dir):
            for name in sorted(files):
                if name.endswith(".py"):
                    path = os.path.join(root, name)
                    z.write(path, os.path.relpath(path, source_dir))
    return buf.getvalue()


def _create_function(lam, **kwargs):
    for attempt in range(ROLE_PROPAGATION_RETRIES):
        try:
            return lam.create_function(**kwargs)["FunctionArn"]
        except ClientError as e:
            role_not_ready = (e.response["Error"]["Code"] == "InvalidParameterValueException"
                              and "cannot be assumed" in str(e))
            if role_not_ready and attempt < ROLE_PROPAGATION_RETRIES - 1:
                print(f"  Role not assumable yet; retrying in {ROLE_PROPAGATION_DELAY_S}s...")
                time.sleep(ROLE_PROPAGATION_DELAY_S)
                continue
            raise


def deploy_lambda(lam, name, role_arn, zip_bytes, env_vars, layers=None, timeout=60):
    """Create the function, or update its code AND configuration (role, layers, env, timeout)."""
    settings = {"Role": role_arn, "Handler": HANDLER, "Runtime": RUNTIME, "Timeout": timeout,
                "Environment": {"Variables": env_vars}, "Layers": layers or []}
    try:
        arn = _create_function(lam, FunctionName=name, Code={"ZipFile": zip_bytes}, **settings)
        print(f"Created Lambda: {name}")
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=name, ZipFile=zip_bytes)
        lam.get_waiter("function_updated").wait(FunctionName=name)
        lam.update_function_configuration(FunctionName=name, **settings)
        lam.get_waiter("function_updated").wait(FunctionName=name)
        arn = lam.get_function(FunctionName=name)["Configuration"]["FunctionArn"]
        print(f"Updated Lambda: {name}")
    lam.get_waiter("function_active").wait(FunctionName=name)
    return arn


def setup_s3_trigger(s3, lam, bucket, function_arn, account_id):
    """Invoke the transform Lambda for every new raw_data/to_process/*.json object.

    Note: this replaces the bucket's whole notification configuration (the bucket is dedicated
    to this pipeline).
    """
    try:
        lam.add_permission(FunctionName=function_arn, StatementId="s3-invoke-transform",
                           Action="lambda:InvokeFunction", Principal="s3.amazonaws.com",
                           SourceArn=f"arn:aws:s3:::{bucket}", SourceAccount=account_id)
    except lam.exceptions.ResourceConflictException:
        pass  # permission already present
    s3.put_bucket_notification_configuration(Bucket=bucket, NotificationConfiguration={
        "LambdaFunctionConfigurations": [{
            "LambdaFunctionArn": function_arn,
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": config.RAW_PREFIX},
                                               {"Name": "suffix", "Value": ".json"}]}},
        }]})
    print(f"Configured S3 trigger: {config.RAW_PREFIX}*.json -> {config.TRANSFORM_FUNCTION}")


def deploy_lambdas(session, bucket, client_id, client_secret, layer_arn=None):
    iam, lam = session.client("iam"), session.client("lambda")
    extract_role = iam.get_role(RoleName=EXTRACT_ROLE)["Role"]["Arn"]
    transform_role = iam.get_role(RoleName=TRANSFORM_ROLE)["Role"]["Arn"]

    # The secret is stored as a Lambda environment variable. See README: Secrets Manager is better.
    deploy_lambda(lam, config.EXTRACT_FUNCTION, extract_role, build_zip(REPO_ROOT / "src" / "extract_lambda"),
                  {"SPOTIFY_CLIENT_ID": client_id, "SPOTIFY_CLIENT_SECRET": client_secret,
                   "S3_BUCKET_NAME": bucket})
    transform_arn = deploy_lambda(
        lam, config.TRANSFORM_FUNCTION, transform_role, build_zip(REPO_ROOT / "src" / "transform_lambda"),
        {"TRANSFORMED_S3_BUCKET": bucket}, layers=[config.pandas_layer_arn(session.region_name, layer_arn)])

    account_id = session.client("sts").get_caller_identity()["Account"]
    setup_s3_trigger(session.client("s3"), lam, bucket, transform_arn, account_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deploy the pipeline Lambdas")
    parser.add_argument("--bucket-name", help=f"Bucket name (default: ${config.BUCKET_ENV_VAR})")
    parser.add_argument("--pandas-layer-arn", help=f"AWS SDK for pandas layer ARN (default: "
                                                   f"${config.PANDAS_LAYER_ENV_VAR}, else the documented "
                                                   f"ARN for the region in infra/lambda_layers.py)")
    args = parser.parse_args(argv)
    session = config.get_session()
    bucket = config.resolve_bucket_name(args.bucket_name)
    client_id, client_secret = get_spotify_credentials()
    deploy_lambdas(session, bucket, client_id, client_secret, args.pandas_layer_arn)


if __name__ == "__main__":
    main()
