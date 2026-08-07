# Automated EBS Snapshot Creation and Cleanup

Automates EBS volume backups using AWS Lambda, tags each snapshot, and deletes snapshots older than a configurable retention period (default: 30 days). Runs on a weekly schedule via Amazon EventBridge.

## Objective

Automate EBS volume backups and clean up old snapshots without manual intervention, using a serverless (Lambda) approach.

## Architecture

```
EventBridge (weekly schedule)
        │
        ▼
   Lambda Function ──► ec2:CreateSnapshot (tags it CreatedBy=Lambda-Backup)
        │
        └──────────► ec2:DescribeSnapshots (filter by tag)
                            │
                            ▼
                     ec2:DeleteSnapshot (if older than 30 days)
```

## Components

| Component | Purpose |
|---|---|
| EBS Volume | The source volume being backed up |
| IAM Role (`Lambda-EBS-Backup-Role`) | Grants Lambda permission to manage snapshots |
| Lambda Function (`ebs-snapshot-backup`) | Creates, tags, lists, and deletes snapshots |
| EventBridge Rule | Triggers the Lambda function weekly |

## Setup

### 1. EBS Volume
Identified an existing EBS volume (or created a new one) and noted its Volume ID for use in the Lambda function.

### 2. IAM Role
Created `Lambda-EBS-Backup-Role` with the Lambda service as the trusted entity, and attached an inline policy (see [`iam-policy.json`](./iam-policy.json)) granting:
- `ec2:CreateSnapshot`
- `ec2:DescribeSnapshots`
- `ec2:DeleteSnapshot`
- `ec2:CreateTags`
- `ec2:DescribeVolumes`
- CloudWatch Logs permissions for execution logging

### 3. Lambda Function
See [`lambda_function.py`](./lambda_function.py). The function:
1. Creates a snapshot of the specified volume
2. Tags it `CreatedBy=Lambda-Backup`
3. Lists all snapshots owned by the account with that tag
4. Deletes any snapshot older than the retention period (30 days)
5. Prints the IDs of created and deleted snapshots to CloudWatch Logs

Runtime: Python 3.12, Timeout: 30 seconds.

### 4. EventBridge Schedule
Added an EventBridge (CloudWatch Events) trigger to the Lambda function with schedule expression:
```
rate(7 days)
```
This runs the backup and cleanup process once a week.

### 5. Testing
Triggered the function manually via the Lambda console **Test** feature. Confirmed:
- Execution status: `Succeeded`
- A new snapshot appeared in **EC2 → Elastic Block Store → Snapshots**
- The snapshot carried the tag `CreatedBy=Lambda-Backup`
- Function logs printed the created snapshot ID (no deletions occurred on first run, as expected — no snapshots yet exceeded the 30-day retention window)

Screenshots of each verification step are included in this repo under `/screenshots`.

## Discussion: Lambda vs. AWS Data Lifecycle Manager (DLM)

AWS Data Lifecycle Manager (DLM) can automate EBS snapshot creation and retention natively, without writing any code. For a simple fixed schedule and simple retention count, DLM is usually the better choice — less to build and maintain.

However, a custom Lambda function is still preferable when you need:

- **Custom retention logic** — e.g., keeping more recent snapshots but fewer as they age (grandfather-father-son schemes), or retention rules based on conditions DLM can't express.
- **Cross-account or cross-region snapshot copies** — DLM supports some cross-region copy, but more complex cross-account sharing/copying workflows are easier to control in Lambda.
- **Notifications and integrations** — e.g., sending a Slack/SNS alert after backup, updating an external tracking system, or triggering downstream workflows (like starting a restore test).
- **Conditional logic** — e.g., only snapshotting if the volume has changed, or skipping snapshots during a maintenance window.

## Repository Structure

```
.
├── README.md
├── lambda_function.py
├── iam-policy.json
└── screenshots/
    ├── iam-role-permissions.png
    ├── lambda-test-success.png
    ├── snapshot-details.png
    ├── snapshot-tags.png
    └── eventbridge-trigger.png
```
