import boto3
import argparse

events_client = boto3.client('events')
lambda_client = boto3.client('lambda')

def setup_eventbridge_trigger(lambda_name, cron_schedule="cron(0 12 * * ? *)"):
    """Creates a CloudWatch Event Rule to trigger the lambda daily at noon UTC by default"""
    
    # 1. Get Lambda ARN
    lambda_response = lambda_client.get_function(FunctionName=lambda_name)
    lambda_arn = lambda_response['Configuration']['FunctionArn']

    rule_name = "SpotifyDailyExtractionRule"
    
    # 2. Put Rule
    print(f"🚀 Creating EventBridge Rule: {rule_name} with schedule: {cron_schedule}")
    rule_response = events_client.put_rule(
        Name=rule_name,
        ScheduleExpression=cron_schedule,
        State='ENABLED',
        Description='Triggers Spotify extraction daily'
    )
    rule_arn = rule_response['RuleArn']

    # 3. Add permission for EventBridge to invoke Lambda
    try:
        lambda_client.add_permission(
            FunctionName=lambda_name,
            StatementId='eventbridge-invoke-permission',
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
        print("  └── Added permission to invoke Lambda")
    except lambda_client.exceptions.ResourceConflictException:
        print("  └── Permission already exists")

    # 4. Put Target
    events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                'Id': '1',
                'Arn': lambda_arn
            }
        ]
    )
    print(f"✅ Successfully attached target Lambda ({lambda_name}) to rule ({rule_name})")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schedule', default='cron(0 12 * * ? *)', help="Cron expression for the schedule")
    args = parser.parse_args()
    
    setup_eventbridge_trigger("SpotifyExtractData", args.schedule)
