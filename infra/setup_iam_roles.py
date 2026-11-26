"""Create the pipeline's IAM roles, with S3 access scoped to the pipeline bucket.

Each role gets one inline policy (SpotifyPipelineS3Access) that allows only the S3 actions its
code calls, on only the prefixes it uses. AmazonS3FullAccess is no longer attached, and is
detached from roles left over from older deployments.

Permissions (derived from the code; NOT tested against AWS, only against moto, which does not
enforce IAM policies):

SpotifyExtractLambdaRole
  - AWSLambdaBasicExecutionRole (AWS managed): create log streams and write CloudWatch Logs.
  - s3:PutObject on <bucket>/raw_data/to_process/*: put_object of the raw Spotify JSON.

SpotifyTransformLambdaRole
  - AWSLambdaBasicExecutionRole (AWS managed): CloudWatch Logs.
  - s3:GetObject on <bucket>/raw_data/to_process/*: read the raw JSON (also the copy_object source).
  - s3:DeleteObject on <bucket>/raw_data/to_process/*: remove the raw file after it is copied.
  - s3:PutObject on <bucket>/raw_data/processed/*: copy_object destination.
  - s3:PutObject on <bucket>/transformed_data/*: awswrangler writes the three Parquet files.

SpotifyGlueCrawlerRole
  - AWSGlueServiceRole (AWS managed): Glue Data Catalog updates and crawler CloudWatch Logs.
    Note: this managed policy also covers S3 buckets named aws-glue-*; none are used here.
  - s3:ListBucket on <bucket>, only for prefix transformed_data/: let the crawler list the Parquet files.
  - s3:GetObject on <bucket>/transformed_data/*: let the crawler read Parquet schemas.
"""
import argparse
import json

import boto3

EXTRACT_ROLE = "SpotifyExtractLambdaRole"
TRANSFORM_ROLE = "SpotifyTransformLambdaRole"
GLUE_ROLE = "SpotifyGlueCrawlerRole"
ROLE_NAMES = (EXTRACT_ROLE, TRANSFORM_ROLE, GLUE_ROLE)
INLINE_POLICY_NAME = "SpotifyPipelineS3Access"

LAMBDA_BASIC_EXECUTION = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
GLUE_SERVICE_ROLE = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
S3_FULL_ACCESS = "arn:aws:iam::aws:policy/AmazonS3FullAccess"  # attached by older versions; removed


def _trust_policy(service):
    return {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}]}


def _policy(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


def extract_s3_policy(bucket):
    return _policy(
        {"Sid": "WriteRawJson", "Effect": "Allow", "Action": ["s3:PutObject"],
         "Resource": [f"arn:aws:s3:::{bucket}/raw_data/to_process/*"]},
    )


def transform_s3_policy(bucket):
    return _policy(
        {"Sid": "ReadAndRemoveRawJson", "Effect": "Allow", "Action": ["s3:GetObject", "s3:DeleteObject"],
         "Resource": [f"arn:aws:s3:::{bucket}/raw_data/to_process/*"]},
        {"Sid": "WriteProcessedAndParquet", "Effect": "Allow", "Action": ["s3:PutObject"],
         "Resource": [f"arn:aws:s3:::{bucket}/raw_data/processed/*",
                      f"arn:aws:s3:::{bucket}/transformed_data/*"]},
    )


def glue_s3_policy(bucket):
    return _policy(
        {"Sid": "ListTransformedPrefix", "Effect": "Allow", "Action": ["s3:ListBucket"],
         "Resource": [f"arn:aws:s3:::{bucket}"],
         "Condition": {"StringLike": {"s3:prefix": ["transformed_data", "transformed_data/*"]}}},
        {"Sid": "ReadParquet", "Effect": "Allow", "Action": ["s3:GetObject"],
         "Resource": [f"arn:aws:s3:::{bucket}/transformed_data/*"]},
    )


def role_specs(bucket):
    """(role name, trusted service, managed policy ARNs, inline S3 policy) for every pipeline role."""
    return [
        (EXTRACT_ROLE, "lambda.amazonaws.com", [LAMBDA_BASIC_EXECUTION], extract_s3_policy(bucket)),
        (TRANSFORM_ROLE, "lambda.amazonaws.com", [LAMBDA_BASIC_EXECUTION], transform_s3_policy(bucket)),
        (GLUE_ROLE, "glue.amazonaws.com", [GLUE_SERVICE_ROLE], glue_s3_policy(bucket)),
    ]


def ensure_role(iam, name, service, managed_policy_arns, inline_policy):
    try:
        arn = iam.create_role(RoleName=name,
                              AssumeRolePolicyDocument=json.dumps(_trust_policy(service)))["Role"]["Arn"]
        print(f"Created role: {name}")
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        print(f"Role {name} already exists; updating its policies.")

    for policy_arn in managed_policy_arns:
        iam.attach_role_policy(RoleName=name, PolicyArn=policy_arn)
    iam.put_role_policy(RoleName=name, PolicyName=INLINE_POLICY_NAME, PolicyDocument=json.dumps(inline_policy))

    attached = iam.list_attached_role_policies(RoleName=name)["AttachedPolicies"]
    if any(p["PolicyArn"] == S3_FULL_ACCESS for p in attached):
        iam.detach_role_policy(RoleName=name, PolicyArn=S3_FULL_ACCESS)
        print(f"  Detached AmazonS3FullAccess from {name}")
    return arn


def setup_roles(iam, bucket):
    return {name: ensure_role(iam, name, service, managed, inline)
            for name, service, managed, inline in role_specs(bucket)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the pipeline's IAM roles")
    parser.add_argument("--bucket-name", required=True, help="Pipeline bucket the roles are scoped to")
    args = parser.parse_args(argv)
    for name, arn in setup_roles(boto3.client("iam"), args.bucket_name).items():
        print(f"{name}: {arn}")


if __name__ == "__main__":
    main()
