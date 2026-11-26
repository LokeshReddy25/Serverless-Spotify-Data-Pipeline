"""Create the Glue database and the crawler over transformed_data/.

Usage: python -m infra.setup_glue_athena --bucket-name NAME
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create the Glue database and crawler")
    parser.add_argument("--bucket-name", help=f"Bucket name (default: ${config.BUCKET_ENV_VAR})")
    args = parser.parse_args(argv)
    session = config.get_session()
    setup_glue(session.client("glue"), session.client("iam"), config.resolve_bucket_name(args.bucket_name))


if __name__ == "__main__":
    main()
