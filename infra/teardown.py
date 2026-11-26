"""Delete every AWS resource that deploy_all.py creates.

Usage:
    python -m infra.teardown --bucket-name NAME          # dry run: lists what would be deleted
    python -m infra.teardown --bucket-name NAME --yes    # deletes

Deletes, in order: the EventBridge rule (and its target), both Lambda functions (their resource
policies go with them), the Lambdas' CloudWatch log groups (created by Lambda at runtime), the Glue
crawler, the Glue database (with any tables the crawler made), every object and object version in
the bucket and then the bucket itself, and the three IAM roles with their policies.
Anything already gone is reported as "not found" and skipped, so it is safe to rerun.
"""
import argparse

from botocore.exceptions import ClientError

from infra import config
from infra.setup_iam_roles import ROLE_NAMES

LAMBDA_FUNCTIONS = (config.EXTRACT_FUNCTION, config.TRANSFORM_FUNCTION)
MISSING_CODES = {"ResourceNotFoundException", "EntityNotFoundException", "NoSuchEntity", "NoSuchBucket",
                 "404", "NotFound"}


def planned_resources(bucket):
    return ([f"EventBridge rule {config.SCHEDULE_RULE}"]
            + [f"Lambda function {f}" for f in LAMBDA_FUNCTIONS]
            + [f"CloudWatch log group /aws/lambda/{f}" for f in LAMBDA_FUNCTIONS]
            + [f"Glue crawler {config.GLUE_CRAWLER}", f"Glue database {config.GLUE_DATABASE} (and its tables)",
               f"S3 bucket {bucket} (all objects and versions)"]
            + [f"IAM role {r}" for r in ROLE_NAMES])


def _attempt(label, action, results):
    try:
        action()
        results.append((label, "deleted"))
    except ClientError as e:
        if e.response["Error"]["Code"] in MISSING_CODES:
            results.append((label, "not found"))
        else:
            raise


def _check_bucket_owner(s3, bucket, account_id):
    """Refuse to touch a bucket with this name that belongs to another account."""
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("403", "AccessDenied"):
            raise SystemExit(f"ERROR: bucket '{bucket}' is not owned by account {account_id}; "
                             "refusing to delete it.") from None
        if code not in MISSING_CODES:
            raise


def _empty_and_delete_bucket(s3, bucket, account_id):
    _check_bucket_owner(s3, bucket, account_id)
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, ExpectedBucketOwner=account_id):
        to_delete = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                     for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        for i in range(0, len(to_delete), 1000):
            s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete[i:i + 1000], "Quiet": True},
                              ExpectedBucketOwner=account_id)
    s3.delete_bucket(Bucket=bucket, ExpectedBucketOwner=account_id)


def _delete_role(iam, role):
    for name in iam.list_role_policies(RoleName=role)["PolicyNames"]:
        iam.delete_role_policy(RoleName=role, PolicyName=name)
    for policy in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]:
        iam.detach_role_policy(RoleName=role, PolicyArn=policy["PolicyArn"])
    iam.delete_role(RoleName=role)


def _delete_rule(events):
    # DeleteRule succeeds even when the rule is already gone, so check first to report accurately.
    events.describe_rule(Name=config.SCHEDULE_RULE)
    try:
        events.remove_targets(Rule=config.SCHEDULE_RULE, Ids=["1"])
    except ClientError as e:
        if e.response["Error"]["Code"] not in MISSING_CODES:
            raise
    events.delete_rule(Name=config.SCHEDULE_RULE)


def teardown(session, bucket):
    events, lam, logs = session.client("events"), session.client("lambda"), session.client("logs")
    glue, s3, iam = session.client("glue"), session.client("s3"), session.client("iam")
    account_id = session.client("sts").get_caller_identity()["Account"]
    results = []

    _attempt(f"EventBridge rule {config.SCHEDULE_RULE}", lambda: _delete_rule(events), results)
    for fn in LAMBDA_FUNCTIONS:
        _attempt(f"Lambda function {fn}", lambda fn=fn: lam.delete_function(FunctionName=fn), results)
    for fn in LAMBDA_FUNCTIONS:
        group = f"/aws/lambda/{fn}"
        _attempt(f"CloudWatch log group {group}", lambda g=group: logs.delete_log_group(logGroupName=g), results)
    try:
        _attempt(f"Glue crawler {config.GLUE_CRAWLER}", lambda: glue.delete_crawler(Name=config.GLUE_CRAWLER),
                 results)
    except glue.exceptions.CrawlerRunningException:
        raise SystemExit(f"ERROR: crawler {config.GLUE_CRAWLER} is running. Wait for it to finish, "
                         "then run teardown again.") from None
    _attempt(f"Glue database {config.GLUE_DATABASE}", lambda: glue.delete_database(Name=config.GLUE_DATABASE),
             results)
    _attempt(f"S3 bucket {bucket}", lambda: _empty_and_delete_bucket(s3, bucket, account_id), results)
    for role in ROLE_NAMES:
        _attempt(f"IAM role {role}", lambda role=role: _delete_role(iam, role), results)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Delete every resource deploy_all.py creates")
    parser.add_argument("--bucket-name", help=f"Bucket name (default: ${config.BUCKET_ENV_VAR})")
    parser.add_argument("--yes", action="store_true", help="Actually delete (default is a dry run)")
    args = parser.parse_args(argv)
    bucket = config.resolve_bucket_name(args.bucket_name)

    if not args.yes:
        print("Dry run. These resources would be deleted (rerun with --yes to delete):")
        for item in planned_resources(bucket):
            print(f"  - {item}")
        return []

    session = config.get_session()
    results = teardown(session, bucket)
    for label, status in results:
        print(f"{status:>9}: {label}")
    return results


if __name__ == "__main__":
    main()
