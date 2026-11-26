"""Deploy the whole pipeline.

Usage:
    python deploy_all.py --bucket-name NAME [--schedule "cron(...)"] [--pandas-layer-arn ARN]
    (or set SPOTIFY_PIPELINE_BUCKET instead of --bucket-name)

AWS credentials come from the standard boto3 chain (AWS_PROFILE / SSO / `aws configure`, or
AWS_ACCESS_KEY_ID etc. in the environment). Nothing is read from a credentials file in the repo.
Spotify credentials come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET or a hidden prompt and are
never passed as command-line arguments or printed.

Remove everything again with: python -m infra.teardown --bucket-name NAME --yes
"""
import argparse

from infra import config, setup_eventbridge, setup_glue_athena, setup_iam_roles, setup_lambda, setup_s3
from infra.spotify_credentials import get_spotify_credentials


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deploy the Spotify pipeline")
    parser.add_argument("--bucket-name", help=f"Fixed bucket name (default: ${config.BUCKET_ENV_VAR})")
    parser.add_argument("--schedule", default=config.DEFAULT_SCHEDULE, help="EventBridge schedule expression")
    parser.add_argument("--pandas-layer-arn", help="Override the AWS SDK for pandas Lambda layer ARN")
    args = parser.parse_args(argv)

    session = config.get_session()
    bucket = config.resolve_bucket_name(args.bucket_name)
    client_id, client_secret = get_spotify_credentials()
    print(f"Deploying to bucket '{bucket}' in {session.region_name}.")

    print("\n[1/5] S3 bucket")
    setup_s3.create_bucket(session.client("s3"), bucket, session.region_name)
    print("\n[2/5] IAM roles")
    setup_iam_roles.setup_roles(session.client("iam"), bucket)
    print("\n[3/5] Lambda functions and S3 trigger")
    setup_lambda.deploy_lambdas(session, bucket, client_id, client_secret, args.pandas_layer_arn)
    print("\n[4/5] EventBridge schedule")
    setup_eventbridge.setup_schedule(session.client("events"), session.client("lambda"), args.schedule)
    print("\n[5/5] Glue database and crawler")
    setup_glue_athena.setup_glue(session.client("glue"), session.client("iam"), bucket)

    print("\nDeployment completed.")


if __name__ == "__main__":
    main()
