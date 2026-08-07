# EC2 Auto-Tagging with Lambda + EventBridge

Automatically tags newly launched EC2 instances for resource tracking,
ownership, and cost allocation — no manual tagging required.

## Objective

Whenever an EC2 instance transitions into the `running` state, an
EventBridge rule triggers a Lambda function that tags the instance with:

- **`LaunchDate`** — the date the instance entered the running state
- **`Environment`** — a static classification tag (e.g. `Dev`)
- **`Owner`** *(bonus)* — the IAM user/role that launched the instance,
  resolved automatically via a CloudTrail lookup

## Architecture

```
EC2 instance launched
        │
        ▼
State changes to "running"
        │
        ▼
EventBridge rule (aws.ec2 / EC2 Instance State-change Notification / state=running)
        │
        ▼
Lambda function (ec2-auto-tagger)
        │
        ├── ec2:CreateTags        → applies LaunchDate, Environment, Owner tags
        └── cloudtrail:LookupEvents → resolves the launching IAM user (bonus)
```

## Project structure

```
ec2-auto-tagging/
├── README.md
├── iam/
│   ├── trust-policy.json          # Lambda service trust policy
│   └── ec2-tagging-policy.json    # Inline permissions policy
├── eventbridge/
│   └── event-pattern.json         # EventBridge rule event pattern
├── lambda/
│   └── lambda_function.py         # Lambda handler (Boto3)
└── screenshots/                   # Test evidence
    ├── 01-ec2-tags-console.png
    ├── 02-cloudwatch-logs-basic-tagging.png
    ├── 03-cloudwatch-logs-cloudtrail-retry.png
    └── 04-cloudwatch-logs-owner-tag-expanded.png
```

## 1. Lambda IAM Role

**Role name:** `EC2AutoTagLambdaRole`
**Trusted entity:** `lambda.amazonaws.com` (see [`iam/trust-policy.json`](iam/trust-policy.json))

**Attached policies:**
- `AWSLambdaBasicExecutionRole` (AWS managed — CloudWatch Logs permissions)
- `EC2TaggingInlinePolicy` (inline, custom — see [`iam/ec2-tagging-policy.json`](iam/ec2-tagging-policy.json)):
  - `ec2:CreateTags`
  - `ec2:DescribeInstances`
  - `cloudtrail:LookupEvents` *(added for the bonus Owner-tag feature)*

## 2. Lambda Function

**Function name:** `ec2-auto-tagger`
**Runtime:** Python 3.12
**Timeout:** increased to 1 minute (default 3s is too short once CloudTrail
lookups with retries were added)

See [`lambda/lambda_function.py`](lambda/lambda_function.py) for the full code. Summary of what it does:

1. Extracts the instance ID from the EventBridge event (`event['detail']['instance-id']`)
2. Builds a `LaunchDate` tag from the current UTC date
3. Looks up CloudTrail for the `RunInstances` event matching that instance
   ID to resolve the launching IAM user (retries up to 3 times, 10s apart,
   to account for CloudTrail indexing latency)
4. Calls `ec2.create_tags()` to apply `LaunchDate`, `Environment`, and `Owner`
5. Prints a confirmation message to CloudWatch Logs

## 3. EventBridge Rule

**Rule name:** `ec2-running-autotag-rule`
**Event bus:** `default`
**Target:** Lambda function `ec2-auto-tagger`

**Event pattern** (see [`eventbridge/event-pattern.json`](eventbridge/event-pattern.json)):

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance State-change Notification"],
  "detail": {
    "state": ["running"]
  }
}
```

## 4. Testing & Evidence

**Test procedure:** launched a t2.micro Ubuntu EC2 instance and waited for
it to reach the `running` state, then verified tags were applied.

| Evidence | Screenshot |
|---|---|
| Tags applied in EC2 console (`Name`, `Environment`, `LaunchDate`) | `screenshots/01-ec2-tags-console.png` |
| CloudWatch Logs confirming Lambda executed and tagged the instance | `screenshots/02-cloudwatch-logs-basic-tagging.png` |

Sample confirmation log output:
```
Successfully tagged instance i-0e2749c12af7d1a3c with [{'Key': 'LaunchDate', 'Value': '2026-07-29'}, {'Key': 'Environment', 'Value': 'Dev'}]
```

## 5. Bonus — CloudTrail Owner Tag

Extended the Lambda to resolve the launching IAM user via
`cloudtrail.lookup_events()`, filtering for the `RunInstances` event tied
to the instance ID, and added it as an `Owner` tag.

**Evidence:**

| Evidence | Screenshot |
|---|---|
| CloudWatch Logs showing retry behavior while waiting on CloudTrail indexing | `screenshots/03-cloudwatch-logs-cloudtrail-retry.png` |
| Expanded log entry showing the final tag set including `Owner` | `screenshots/04-cloudwatch-logs-owner-tag-expanded.png` |

Sample log output:
```
Successfully tagged instance i-047b748bdf59f9d54 with [{'Key': 'LaunchDate', 'Value': '2026-07-29'}, {'Key': 'Environment', 'Value': 'Dev'}, {'Key': 'Owner', 'Value': 'Unknown'}]
```

### Known limitation

`cloudtrail.lookup_events()` is not real-time — newly generated
`RunInstances` events can take longer than the Lambda's retry window
(30 seconds in this test) to become queryable, which is why `Owner`
resolved to `Unknown` in this run. Confirmed via CloudTrail Event
History that the `RunInstances` event did exist for the instance, just
not within the retry window.

**Production-grade fix:** rather than polling `LookupEvents` synchronously
inside the tagging Lambda, route CloudTrail logs to an S3 bucket and query
via Athena, or configure CloudTrail to deliver events directly to
EventBridge and trigger a separate enrichment step once the event is
actually available — avoiding the indexing-latency race condition
entirely.

## Deployment (recap)

1. Create the IAM role and attach the trust + inline policies (`iam/`)
2. Create the Lambda function, paste in `lambda/lambda_function.py`, set
   the execution role, and increase the timeout to 1 minute
3. Create the EventBridge rule with the pattern in `eventbridge/event-pattern.json`,
   targeting the Lambda function
4. Launch a test EC2 instance and confirm tags appear within ~30-60 seconds
