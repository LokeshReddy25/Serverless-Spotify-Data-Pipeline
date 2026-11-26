"""Deploy the whole pipeline.

Usage:
    python deploy_all.py --bucket-name NAME [--schedule "cron(...)"] [--pandas-layer-arn ARN] [--run-crawler]
    (or set SPOTIFY_PIPELINE_BUCKET instead of --bucket-name)

AWS credentials come from the standard boto3 chain (AWS_PROFILE / SSO / `aws configure`, or
AWS_ACCESS_KEY_ID etc. in the environment). Nothing is read from a credentials file in the repo.
Spotify credentials come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET or a hidden prompt and are
never passed as command-line arguments or printed.

Remove everything again with: python -m infra.teardown --bucket-name NAME --yes
"""
import argparse

from infra import (config, run_crawler, setup_eventbridge, setup_glue_athena, setup_iam_roles, setup_lambda,
                   setup_s3)
from infra.spotify_credentials import get_spotify_credentials


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deploy the Spotify pipeline")
    parser.add_argument("--bucket-name", help=f"Fixed bucket name (default: ${config.BUCKET_ENV_VAR})")
    parser.add_argument("--schedule", default=config.DEFAULT_SCHEDULE, help="EventBridge schedule expression")
    parser.add_argument("--pandas-layer-arn", help="AWS SDK for pandas layer ARN (default: $PANDAS_LAYER_ARN, "
                        "else the documented ARN for the region in infra/lambda_layers.py)")
    parser.add_argument("--run-crawler", action="store_true",
                        help="Start the Glue crawler at the end (useful on redeploys, once data exists)")
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
    print("\n[5/5] Glue database, crawler and Athena workgroup")
    setup_glue_athena.setup_glue_and_athena(session, bucket)
    if args.run_crawler:
        run_crawler.start_crawler(session.client("glue"))

    print("\nDeployment completed.")
    if not args.run_crawler:
        print("After the pipeline has written data, catalog it with: python -m infra.run_crawler --wait")
    print(f"Query in Athena with workgroup '{config.ATHENA_WORKGROUP}' and database '{config.GLUE_DATABASE}'.")


if __name__ == "__main__":
    main()
