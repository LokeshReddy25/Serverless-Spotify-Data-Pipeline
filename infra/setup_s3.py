"""Create the pipeline bucket (fixed, configurable name) and block public access on it.

Usage: python -m infra.setup_s3 --bucket-name NAME   (or set SPOTIFY_PIPELINE_BUCKET)
"""
import argparse

from botocore.exceptions import ClientError

from infra import config


def create_bucket(s3, bucket, region):
    kwargs = {"Bucket": bucket}
    if region != "us-east-1":  # us-east-1 rejects an explicit LocationConstraint
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        s3.create_bucket(**kwargs)
        print(f"Created bucket: {bucket} ({region})")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "BucketAlreadyOwnedByYou":
            print(f"Bucket {bucket} already exists in your account; reusing it.")
        elif code == "BucketAlreadyExists":
            raise SystemExit(
                f"ERROR: the bucket name '{bucket}' is already used by another AWS account. "
                f"S3 bucket names are global; choose a different name with --bucket-name or "
                f"{config.BUCKET_ENV_VAR}.") from None
        else:
            raise

    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True,
        "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    print("  Public access blocked.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the pipeline S3 bucket")
    parser.add_argument("--bucket-name", help=f"Bucket name (default: ${config.BUCKET_ENV_VAR})")
    args = parser.parse_args(argv)
    session = config.get_session()
    create_bucket(session.client("s3"), config.resolve_bucket_name(args.bucket_name), session.region_name)


if __name__ == "__main__":
    main()
