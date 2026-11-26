import boto3
import argparse

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

    # 2. Glue crawler role (created and scoped to the bucket by setup_iam_roles.py)
    role_arn = iam_client.get_role(RoleName="SpotifyGlueCrawlerRole")['Role']['Arn']

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
