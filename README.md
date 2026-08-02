# dr-rebuild-from-snapshot

A small AWS Lambda function (Python 3.12) that automates a simple disaster
recovery flow:

1. Finds the most recent **completed** EBS snapshot matching a tag
   (`App=DRDemo` by default).
2. Registers a new AMI from that snapshot.
3. Waits for the AMI to become available.
4. Launches a replacement EC2 instance from the new AMI.

## Files

- `lambda_function.py` — the Lambda handler.
- `iam-policy.json` — the inline IAM policy required by the Lambda execution role.

## Deployment

1. Create an IAM role (`DR-Rebuild-Lambda-Role`) trusted by the Lambda service,
   attach the inline policy in `iam-policy.json`, and also attach the AWS
   managed policy `AWSLambdaBasicExecutionRole`.
2. Create a Lambda function (`dr-rebuild-from-snapshot`), runtime Python 3.12,
   using that role. Paste in `lambda_function.py`.
3. Set the Lambda timeout to at least 2–3 minutes (the `image_available`
   waiter can take 30–90s+).
4. Configure environment variables:

   | Key | Value |
   |---|---|
   | `SNAPSHOT_TAG_KEY` | `App` |
   | `SNAPSHOT_TAG_VALUE` | `DRDemo` |
   | `INSTANCE_TYPE` | `t3.micro` |
   | `SUBNET_ID` | your subnet, e.g. `subnet-0abc123` |
   | `SECURITY_GROUP_ID` | a security group allowing SSH, e.g. `sg-0abc123` |

5. Tag your source EBS volume and its snapshots with `App=DRDemo` (or your
   own tag key/value, matching the env vars above).
6. Test manually from the Lambda console with an empty `{}` event.

## Notes

- `RootDeviceName` must match the original AMI's root device (`/dev/xvda`
  for Amazon Linux, `/dev/sda1` for many others).
- If your account has no default VPC, `SUBNET_ID` must be set or
  `run_instances` will fail.
- This is a learning/demo project — the IAM policy uses `Resource: "*"`,
  which should be scoped down before any production use.
