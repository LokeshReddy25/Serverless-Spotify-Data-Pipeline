"""Create the Glue database, the crawler over transformed_data/, and an Athena workgroup.

Usage: python -m infra.setup_glue_athena --bucket-name NAME

The crawler is created but not started here, because right after deployment there is no data to
crawl. Start it with `python -m infra.run_crawler --wait` (or `deploy_all.py --run-crawler`).
The Athena workgroup writes query results to s3://<bucket>/athena_results/ and cancels any query
that would scan more than ATHENA_BYTES_SCANNED_CUTOFF bytes.
"""
import argparse

from infra import config
from infra.setup_iam_roles import GLUE_ROLE


def setup_glue(glue, iam, bucket):
    try:
        glue.create_database(DatabaseInput={"Name": config.GLUE_DATABASE,
                                            "Description": "Database for Spotify Analytics Pipeline"})
        print(f"Created Glue database: {config.GLUE_DATABASE}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {config.GLUE_DATABASE} already exists.")

    crawler = {
        "Name": config.GLUE_CRAWLER,
        "Role": iam.get_role(RoleName=GLUE_ROLE)["Role"]["Arn"],
        "DatabaseName": config.GLUE_DATABASE,
        "Targets": {"S3Targets": [{"Path": f"s3://{bucket}/{config.TRANSFORMED_PREFIX}"}]},
        "SchemaChangePolicy": {"UpdateBehavior": "UPDATE_IN_DATABASE", "DeleteBehavior": "DEPRECATE_IN_DATABASE"},
        "RecrawlPolicy": {"RecrawlBehavior": "CRAWL_EVERYTHING"},
    }
    try:
        glue.create_crawler(**crawler)
        print(f"Created Glue crawler: {config.GLUE_CRAWLER}")
    except glue.exceptions.AlreadyExistsException:
        glue.update_crawler(**crawler)
        print(f"Updated Glue crawler: {config.GLUE_CRAWLER}")


def athena_output_location(bucket):
    return f"s3://{bucket}/{config.ATHENA_RESULTS_PREFIX}"


def workgroup_exists(athena, name=config.ATHENA_WORKGROUP):
    kwargs = {}
    while True:  # botocore has no paginator for list_work_groups
        page = athena.list_work_groups(**kwargs)
        if any(wg["Name"] == name for wg in page["WorkGroups"]):
            return True
        if not page.get("NextToken"):
            return False
        kwargs["NextToken"] = page["NextToken"]


def setup_athena_workgroup(athena, bucket):
    output = athena_output_location(bucket)
    if workgroup_exists(athena):
        athena.update_work_group(WorkGroup=config.ATHENA_WORKGROUP, ConfigurationUpdates={
            "ResultConfigurationUpdates": {"OutputLocation": output},
            "EnforceWorkGroupConfiguration": True,
            "BytesScannedCutoffPerQuery": config.ATHENA_BYTES_SCANNED_CUTOFF,
        })
        print(f"Updated Athena workgroup: {config.ATHENA_WORKGROUP} -> {output}")
    else:
        athena.create_work_group(
            Name=config.ATHENA_WORKGROUP,
            Description="Queries over the Spotify pipeline's Glue database",
            Configuration={
                "ResultConfiguration": {"OutputLocation": output},
                "EnforceWorkGroupConfiguration": True,
                "PublishCloudWatchMetricsEnabled": True,
                "BytesScannedCutoffPerQuery": config.ATHENA_BYTES_SCANNED_CUTOFF,
            })
        print(f"Created Athena workgroup: {config.ATHENA_WORKGROUP} -> {output}")


def setup_glue_and_athena(session, bucket):
    setup_glue(session.client("glue"), session.client("iam"), bucket)
    setup_athena_workgroup(session.client("athena"), bucket)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the Glue database, crawler and Athena workgroup")
    parser.add_argument("--bucket-name", help=f"Bucket name (default: ${config.BUCKET_ENV_VAR})")
    args = parser.parse_args(argv)
    setup_glue_and_athena(config.get_session(), config.resolve_bucket_name(args.bucket_name))


if __name__ == "__main__":
    main()
