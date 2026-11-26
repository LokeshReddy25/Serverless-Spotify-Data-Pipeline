import boto3
import os
import zipfile
import argparse
import time

from spotify_credentials import get_spotify_credentials

lambda_client = boto3.client('lambda')
s3_client = boto3.client('s3')
iam_client = boto3.client('iam')

def create_zip(source_dir, output_filename):
    print(f"📦 Zipping {source_dir} to {output_filename}")
    with zipfile.ZipFile(output_filename, 'w') as z:
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    z.write(file_path, arcname)

def deploy_lambda(function_name, role_arn, zip_file, handler, env_vars, layers=None, timeout=60):
    try:
        with open(zip_file, 'rb') as f:
            zip_content = f.read()

        kwargs = {
            'FunctionName': function_name,
            'Runtime': 'python3.10',
            'Role': role_arn,
            'Handler': handler,
            'Code': {'ZipFile': zip_content},
            'Timeout': timeout,
            'Environment': {'Variables': env_vars}
        }
        if layers:
            kwargs['Layers'] = layers

        response = lambda_client.create_function(**kwargs)
        print(f"✅ Created Lambda: {function_name}")
        return response['FunctionArn']

    except lambda_client.exceptions.ResourceConflictException:
        print(f"Lambda {function_name} already exists. Updating code...")
        with open(zip_file, 'rb') as f:
            lambda_client.update_function_code(FunctionName=function_name, ZipFile=f.read())
        
        # Wait for the update to complete before updating configuration
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)
        
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': env_vars},
            Timeout=timeout
        )
        print(f"✅ Updated Lambda: {function_name}")
        return lambda_client.get_function(FunctionName=function_name)['Configuration']['FunctionArn']

def setup_s3_trigger(bucket_name, lambda_arn):
    """Wait for Lambda active state, add permission, and attach S3 trigger"""
    # Important: Give Lambda permission to be invoked by S3
    try:
        lambda_client.add_permission(
            FunctionName=lambda_arn,
            StatementId=f's3-trigger-{bucket_name}',
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com',
            SourceArn=f"arn:aws:s3:::{bucket_name}"
        )
        print("  └── Added S3 Invoke Permission to Transform Lambda")
    except lambda_client.exceptions.ResourceConflictException:
        pass # Permission already exists

    # Configure S3 bucket notification
    notification_config = {
        'LambdaFunctionConfigurations': [
            {
                'LambdaFunctionArn': lambda_arn,
                'Events': ['s3:ObjectCreated:*'],
                'Filter': {
                    'Key': {
                        'FilterRules': [
                            {'Name': 'prefix', 'Value': 'raw_data/to_process/'},
                            {'Name': 'suffix', 'Value': '.json'}
                        ]
                    }
                }
            }
        ]
    }
    
    s3_client.put_bucket_notification_configuration(
        Bucket=bucket_name,
        NotificationConfiguration=notification_config
    )
    print(f"✅ Configured S3 Trigger: raw_data/to_process/*.json will trigger Transform Lambda")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Deploy Lambdas")
    parser.add_argument('--bucket-name', required=True)
    args = parser.parse_args()
    # Spotify credentials come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET or a hidden prompt,
    # never from command-line arguments (which are visible in process listings and shell history).
    client_id, client_secret = get_spotify_credentials()

    # Need role ARNs from setup_iam_roles
    extract_role = iam_client.get_role(RoleName="SpotifyExtractLambdaRole")['Role']['Arn']
    transform_role = iam_client.get_role(RoleName="SpotifyTransformLambdaRole")['Role']['Arn']

    # 1. Package & Deploy Extract Lambda
    create_zip('src/extract_lambda', 'extract_lambda.zip')
    extract_lambda_arn = deploy_lambda(
        function_name="SpotifyExtractData",
        role_arn=extract_role,
        zip_file="extract_lambda.zip",
        handler="lambda_function.lambda_handler",
        env_vars={
            'SPOTIFY_CLIENT_ID': client_id,
            'SPOTIFY_CLIENT_SECRET': client_secret,
            'S3_BUCKET_NAME': args.bucket_name
        }
    )

    # 2. Package & Deploy Transform Lambda
    # We use AWS Data Wrangler managed layer for Pandas and awswrangler
    current_region = boto3.Session().region_name or 'ap-south-1'
    wrangler_layer_arn = f"arn:aws:lambda:{current_region}:336392948345:layer:AWSSDKPandas-Python310:14"

    create_zip('src/transform_lambda', 'transform_lambda.zip')
    transform_lambda_arn = deploy_lambda(
        function_name="SpotifyTransformData",
        role_arn=transform_role,
        zip_file="transform_lambda.zip",
        handler="lambda_function.lambda_handler",
        env_vars={'TRANSFORMED_S3_BUCKET': args.bucket_name},
        layers=[wrangler_layer_arn]
    )

    # Clean up zip files
    os.remove('extract_lambda.zip')
    os.remove('transform_lambda.zip')

    # Wait a few seconds for IAM attachment and Lambda states to propagate
    print("Sleeping for 5s to allow resources to propagate...")
    time.sleep(5)

    # 3. Add S3 event trigger for Transform Lambda
    setup_s3_trigger(args.bucket_name, transform_lambda_arn)
    
    print("\n✅ All Lambdas Deployed Successfully!")
