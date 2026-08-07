import boto3
import os
from datetime import datetime

ec2 = boto3.client("ec2")

# ---- Configuration (edit these or pass via event / env vars) ----
TAG_KEY = os.environ.get("SNAPSHOT_TAG_KEY", "App")
TAG_VALUE = os.environ.get("SNAPSHOT_TAG_VALUE", "DRDemo")
INSTANCE_TYPE = os.environ.get("INSTANCE_TYPE", "t3.micro")
SUBNET_ID = os.environ.get("SUBNET_ID")            # optional, recommended
SECURITY_GROUP_ID = os.environ.get("SECURITY_GROUP_ID")  # optional


def lambda_handler(event, context):
    # 1. Find the most recent completed snapshot with the tag
    response = ec2.describe_snapshots(
        Filters=[
            {"Name": f"tag:{TAG_KEY}", "Values": [TAG_VALUE]},
            {"Name": "status", "Values": ["completed"]},
        ],
        OwnerIds=["self"]
    )
    snapshots = response.get("Snapshots", [])
    if not snapshots:
        print(f"No completed snapshots found with tag {TAG_KEY}={TAG_VALUE}")
        return {"error": "No completed snapshots found"}

    latest_snapshot = max(snapshots, key=lambda s: s["StartTime"])
    snapshot_id = latest_snapshot["SnapshotId"]
    volume_size = latest_snapshot["VolumeSize"]
    print(f"Most recent snapshot: {snapshot_id} (started {latest_snapshot['StartTime']})")

    # 2. Register a new AMI from that snapshot
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    register_response = ec2.register_image(
        Name=f"dr-restore-{snapshot_id}-{timestamp}",
        Description=f"DR restore built from {snapshot_id}",
        Architecture="x86_64",
        RootDeviceName="/dev/xvda",
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {
                    "SnapshotId": snapshot_id,
                    "VolumeSize": volume_size,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }
        ],
        VirtualizationType="hvm",
        EnaSupport=True,
    )
    ami_id = register_response["ImageId"]
    print(f"Registered AMI: {ami_id}")

    # 3. Wait for AMI to become available
    waiter = ec2.get_waiter("image_available")
    waiter.wait(ImageIds=[ami_id], WaiterConfig={"Delay": 10, "MaxAttempts": 30})
    print(f"AMI {ami_id} is now available")

    # 4. Launch a new instance from the AMI
    run_kwargs = {
        "ImageId": ami_id,
        "InstanceType": INSTANCE_TYPE,
        "MinCount": 1,
        "MaxCount": 1,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": f"dr-restored-{timestamp}"},
                    {"Key": "RestoredFrom", "Value": snapshot_id},
                    {"Key": TAG_KEY, "Value": TAG_VALUE},
                ],
            }
        ],
    }
    if SUBNET_ID:
        run_kwargs["SubnetId"] = SUBNET_ID
    if SECURITY_GROUP_ID:
        run_kwargs["SecurityGroupIds"] = [SECURITY_GROUP_ID]

    run_response = ec2.run_instances(**run_kwargs)
    new_instance_id = run_response["Instances"][0]["InstanceId"]
    print(f"Launched new instance: {new_instance_id}")

    return {
        "snapshot_id": snapshot_id,
        "ami_id": ami_id,
        "new_instance_id": new_instance_id,
    }
