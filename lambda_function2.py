import boto3
from datetime import datetime, timezone, timedelta

VOLUME_ID = "vol-XXXXXXXXXXXXXXXXX"  # <-- replace with your volume ID
RETENTION_DAYS = 30
TAG_KEY = "CreatedBy"
TAG_VALUE = "Lambda-Backup"

ec2 = boto3.client("ec2")


def lambda_handler(event, context):
    # 1. Create snapshot
    snapshot = ec2.create_snapshot(
        VolumeId=VOLUME_ID,
        Description=f"Automated backup of {VOLUME_ID}"
    )
    snapshot_id = snapshot["SnapshotId"]

    ec2.create_tags(
        Resources=[snapshot_id],
        Tags=[{"Key": TAG_KEY, "Value": TAG_VALUE}]
    )
    print(f"Created snapshot: {snapshot_id}")

    # 2. Find old snapshots with our tag, owned by us
    response = ec2.describe_snapshots(
        OwnerIds=["self"],
        Filters=[{"Name": f"tag:{TAG_KEY}", "Values": [TAG_VALUE]}]
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    deleted_ids = []

    for snap in response["Snapshots"]:
        if snap["StartTime"] < cutoff:
            ec2.delete_snapshot(SnapshotId=snap["SnapshotId"])
            deleted_ids.append(snap["SnapshotId"])
            print(f"Deleted old snapshot: {snap['SnapshotId']}")

    print(f"Summary -> Created: {snapshot_id}, Deleted: {deleted_ids}")

    return {
        "created": snapshot_id,
        "deleted": deleted_ids
    }
