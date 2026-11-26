"""Schedule the extract Lambda with an EventBridge rule (default: daily at 12:00 UTC).

Usage: python -m infra.setup_eventbridge [--schedule "cron(0 12 * * ? *)"]
"""
import argparse

from infra import config

STATEMENT_ID = "eventbridge-invoke-permission"


def setup_schedule(events, lam, schedule=config.DEFAULT_SCHEDULE, function_name=config.EXTRACT_FUNCTION):
    function_arn = lam.get_function(FunctionName=function_name)["Configuration"]["FunctionArn"]
    rule_arn = events.put_rule(Name=config.SCHEDULE_RULE, ScheduleExpression=schedule, State="ENABLED",
                               Description="Triggers Spotify extraction daily")["RuleArn"]
    print(f"EventBridge rule {config.SCHEDULE_RULE}: {schedule}")
    try:
        lam.add_permission(FunctionName=function_name, StatementId=STATEMENT_ID,
                           Action="lambda:InvokeFunction", Principal="events.amazonaws.com", SourceArn=rule_arn)
    except lam.exceptions.ResourceConflictException:
        pass  # permission already present
    events.put_targets(Rule=config.SCHEDULE_RULE, Targets=[{"Id": "1", "Arn": function_arn}])
    print(f"  Target: {function_name}")
    return rule_arn


def main(argv=None):
    parser = argparse.ArgumentParser(description="Schedule the extract Lambda")
    parser.add_argument("--schedule", default=config.DEFAULT_SCHEDULE, help="EventBridge schedule expression")
    args = parser.parse_args(argv)
    session = config.get_session()
    setup_schedule(session.client("events"), session.client("lambda"), args.schedule)


if __name__ == "__main__":
    main()
