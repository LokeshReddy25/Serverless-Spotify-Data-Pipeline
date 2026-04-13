import boto3
import json
import argparse
import time

glue_client = boto3.client('glue')
iam_client = boto3.client('iam')
athena_client = boto3.client('athena')

def setup_glue_crawler(bucket_name, database_name="spotify_db", crawler_name="spotify_data_crawler"):
    print("🚀 Setting up Glue and Athena...")
    
    # 1. Create Glue Database
    try:
        glue_client.create_database(
            DatabaseInput={
                'Name': database_name,
                'Description': 'Database for Spotify Analytics Pipeline'
            }
        )
        print(f"✅ Created Glue Database: {database_name}")
    except glue_client.exceptions.AlreadyExistsException:
        print(f"  └── Database {database_name} already exists.")

    # 2. Create IAM Role for Glue
    role_name = "SpotifyGlueCrawlerRole"
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "glue.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy)
        )
        role_arn = role_response['Role']['Arn']
        print(f"✅ Created Glue IAM Role: {role_name}")
    except iam_client.exceptions.EntityAlreadyExistsException:
        role_arn = iam_client.get_role(RoleName=role_name)['Role']['Arn']
        print(f"  └── Glue role {role_name} already exists.")

    iam_client.attach_role_policy(RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole")
    iam_client.attach_role_policy(RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AmazonS3FullAccess")
    time.sleep(5) # Wait for role creation propagation

    # 3. Create Glue Crawler
    target_path = f"s3://{bucket_name}/transformed_data/"
    try:
        glue_client.create_crawler(
            Name=crawler_name,
            Role=role_arn,
            DatabaseName=database_name,
            Targets={'S3Targets': [{'Path': target_path}]},
            SchemaChangePolicy={'UpdateBehavior': 'UPDATE_IN_DATABASE', 'DeleteBehavior': 'DEPRECATE_IN_DATABASE'},
            RecrawlPolicy={'RecrawlBehavior': 'CRAWL_EVERYTHING'}
        )
        print(f"✅ Created Glue Crawler: {crawler_name} pointing to {target_path}")
    except glue_client.exceptions.AlreadyExistsException:
        print(f"  └── Crawler {crawler_name} already exists. Updating its target path...")
        glue_client.update_crawler(
            Name=crawler_name,
            Role=role_arn,
            DatabaseName=database_name,
            Targets={'S3Targets': [{'Path': target_path}]},
            SchemaChangePolicy={'UpdateBehavior': 'UPDATE_IN_DATABASE', 'DeleteBehavior': 'DEPRECATE_IN_DATABASE'},
            RecrawlPolicy={'RecrawlBehavior': 'CRAWL_EVERYTHING'}
        )
        print(f"✅ Updated Crawler: {crawler_name} target to {target_path}")

    print(f"\n✅ You can now run the crawler from the AWS Console to catalog the parquet files.")
    print("Tip: Run it after executing the Extract & Transform Lambdas at least once.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket-name', required=True)
    args = parser.parse_args()
    
    setup_glue_crawler(args.bucket_name)
