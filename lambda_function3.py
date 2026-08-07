"""
EC2 Auto-Tagging Lambda
-----------------------
Triggered by an EventBridge rule whenever an EC2 instance enters the
'running' state. Tags the instance with:
  - LaunchDate: the current date (UTC)
  - Environment: a static value (customize as needed)
  - Owner: the IAM user/role that launched the instance, resolved via
           a CloudTrail RunInstances event lookup (bonus feature)
"""

import boto3
import datetime
import time

ec2 = boto3.client('ec2')
cloudtrail = boto3.client('cloudtrail')


def get_launching_user(instance_id, retries=3, delay=10):
    """
    Look up CloudTrail for the RunInstances event tied to this instance ID
    to identify who launched it. CloudTrail's LookupEvents API has some
    indexing latency, so this retries a few times with a short delay
    before giving up and returning 'Unknown'.
    """
    for attempt in range(retries):
        try:
            response = cloudtrail.lookup_events(
                LookupAttributes=[
                    {'AttributeKey': 'ResourceName', 'AttributeValue': instance_id}
                ],
                MaxResults=10
            )
            for event in response.get('Events', []):
                if event['EventName'] == 'RunInstances':
                    return event.get('Username', 'Unknown')
        except Exception as e:
            print(f"CloudTrail lookup error (attempt {attempt + 1}): {e}")

        print(f"No RunInstances event found yet for {instance_id}, retrying...")
        time.sleep(delay)

    return 'Unknown'


def lambda_handler(event, context):
    # 1. Extract instance ID from the EventBridge event
    instance_id = event['detail']['instance-id']

    # 2. Build the LaunchDate tag
    launch_date = datetime.datetime.utcnow().strftime('%Y-%m-%d')

    # 3. Resolve the launching IAM user via CloudTrail (bonus)
    owner = get_launching_user(instance_id)

    tags = [
        {'Key': 'LaunchDate', 'Value': launch_date},
        {'Key': 'Environment', 'Value': 'Dev'},
        {'Key': 'Owner', 'Value': owner}
    ]

    # 4. Apply tags
    ec2.create_tags(
        Resources=[instance_id],
        Tags=tags
    )

    # 5. Confirmation message
    print(f"Successfully tagged instance {instance_id} with {tags}")

    return {
        'statusCode': 200,
        'body': f'Tagged instance {instance_id}, Owner: {owner}'
    }
