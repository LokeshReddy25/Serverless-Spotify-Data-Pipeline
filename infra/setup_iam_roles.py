import boto3
import json

iam_client = boto3.client('iam')

def create_role(role_name, assume_role_policy):
    try:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        print(f"✅ Created role: {role_name}")
        return response['Role']['Arn']
    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"Role {role_name} already exists.")
        return iam_client.get_role(RoleName=role_name)['Role']['Arn']

def attach_policy(role_name, policy_arn):
    iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=policy_arn
    )
    print(f"  └── Attached policy: {policy_arn} to {role_name}")

def setup_roles():
    print("🚀 Setting up IAM Roles...")

    # Trust policy for Lambda
    lambda_trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    # Extract Lambda Role
    extract_role_name = "SpotifyExtractLambdaRole"
    extract_role_arn = create_role(extract_role_name, lambda_trust_policy)
    
    # Attach Basic Execution Role (for CloudWatch Logs)
    attach_policy(extract_role_name, "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    # Attach S3 Full Access (Simplified for development, should be scoped down in prod)
    attach_policy(extract_role_name, "arn:aws:iam::aws:policy/AmazonS3FullAccess")

    # Transform Lambda Role
    transform_role_name = "SpotifyTransformLambdaRole"
    transform_role_arn = create_role(transform_role_name, lambda_trust_policy)
    
    # Attach policies
    attach_policy(transform_role_name, "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
    attach_policy(transform_role_name, "arn:aws:iam::aws:policy/AmazonS3FullAccess")

    print(f"\n✅ IAM Roles Setup Complete!")
    print(f"Extract Role ARN: {extract_role_arn}")
    print(f"Transform Role ARN: {transform_role_arn}")

if __name__ == '__main__':
    setup_roles()
