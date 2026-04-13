import boto3
import argparse
import sys
from botocore.exceptions import ClientError

def create_bucket(bucket_name, region=None):
    """Create an S3 bucket in a specified region"""
    try:
        if region is None:
            s3_client = boto3.client('s3')
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client = boto3.client('s3', region_name=region)
            location = {'LocationConstraint': region}
            s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=location)
        print(f"✅ Successfully created bucket: {bucket_name}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
            print(f"Bucket {bucket_name} already exists and is owned by you.")
        else:
            print(f"❌ Error creating bucket: {e}")
            sys.exit(1)

def create_folder_structure(bucket_name):
    """Create simulated folder structure in S3 for clear organization"""
    s3_client = boto3.client('s3')
    
    folders = [
        'raw_data/to_process/',
        'raw_data/processed/',
        'transformed_data/albums/',
        'transformed_data/artists/',
        'transformed_data/tracks/'
    ]
    
    for folder in folders:
        try:
            s3_client.put_object(Bucket=bucket_name, Key=folder)
            print(f"  └── Created prefix: {folder}")
        except ClientError as e:
            print(f"❌ Error creating folder {folder}: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Setup S3 for Spotify ETL Pipeline")
    parser.add_argument('--bucket-name', required=True, help="Name of the S3 bucket to create (must be globally unique)")
    
    args = parser.parse_args()
    
    region = boto3.Session().region_name or 'us-east-1'
    
    # In us-east-1, AWS does not accept the LocationConstraint parameter
    location_constraint = region if region != 'us-east-1' else None
    
    print("🚀 Setting up S3 Infrastructure...")
    create_bucket(args.bucket_name, location_constraint)
    create_folder_structure(args.bucket_name)
    print("✅ S3 Setup Complete!")
