---
title: "Deploy LocalStack on VPS: Complete Guide to Local AWS Cloud Emulation"
date: 2026-09-02
description: "Skip AWS billing entirely. Deploy LocalStack on your VPS to locally emulate S3, Lambda, DynamoDB, SQS and 200+ AWS services for zero-cost development and testing."
tags: ["LocalStack", "AWS", "VPS", "Dev Environment", "Docker", "S3", "Lambda", "Self-hosted", "Cost Savings"]
categories: ["Cloud Savings"]
image: "/images/posts/vps-localstack-aws-simulator/featured-en.png"
draft: false
---

## Introduction

Have you ever faced these scenarios:

- You built an app that uploads files to S3, only to discover the AWS Access Key was misconfigured at deployment time;
- You want to test Lambda functions locally, but have to push to the cloud every time to run them;
- You need to test DynamoDB query performance, but worry about real costs from test data;
- Your team's CI/CD pipeline depends on AWS services, and every test run consumes budget.

**LocalStack solves all of these problems.**

LocalStack is an open-source local cloud development and testing framework that emulates **200+ AWS services** on your local machine or VPS, including S3, Lambda, DynamoDB, SQS, SNS, Kinesis, ECS, RDS, and more. Your application code requires zero changes — simply point the AWS SDK endpoint to LocalStack, and you can complete all development and testing locally.

This guide walks you through deploying LocalStack on a VPS from scratch, including Docker Compose configuration, common service usage, AWS SDK integration, and real project implementation examples.

---

## Why Run LocalStack on a VPS?

| Approach | Cost | Network Latency | Persistence | Team Collaboration |
|----------|------|-----------------|-------------|-------------------|
| Local PC with LocalStack | Free | None | Local disk | Each member deploys independently |
| AWS Local (paid) | High (instance costs) | Low | Cloud storage | Easy to share |
| **VPS with LocalStack** | **Low (fixed monthly)** | **Low** | **Cloud persistent storage** | **Single shared instance for the team** |

The core advantage of the VPS approach: **a low-spec VPS (2C2G) runs it fine, and all team members access the same instance through a single endpoint, ensuring identical dev and test environments.**

---

## 1. Quick Start: One-Command Docker Compose Deployment

### 1.1 Full Version (Recommended)

Create `docker-compose.yml`:

```yaml
services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"          # LocalStack main port
      - "4510-4559:4510-4559" # Extended port range
    environment:
      - SERVICES=s3,lambda,dynamodb,sns,sqs,sts,kinesis,ecr,iam,secretsmanager,apigateway,events,redshift,rds,cloudformation,cloudwatch,firelens,es,kms,ssm,stepfunctions,codepipeline,glue,config,transcribe,neptune,sagemaker
      - EDGE_PORT=4566
      - PERSISTENCE=1         # Enable data persistence
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - ./localstack-data:/var/lib/localstack  # Data persistence
      - /var/run/docker.sock:/var/run/docker.sock  # Required for Lambda container management
    networks:
      - localstack-net

networks:
  localstack-net:
    driver: bridge
```

Start the service:

```bash
docker compose up -d
```

Verify deployment:

```bash
curl http://localhost:4566/_localstack/health
```

Expected response:

```json
{
  "services": {
    "s3": "running",
    "lambda": "running",
    "dynamodb": "running",
    "sts": "available"
  },
  "edges": {
    "0.0.0.0:4566": "running"
  }
}
```

### 1.2 Minimal Version (Resource-Saving)

If you only need the most common services:

```yaml
environment:
  - SERVICES=s3,lambda,dynamodb,sqs,sns,sts
  - EDGE_PORT=4566
  - PERSISTENCE=1
  - AWS_DEFAULT_REGION=us-east-1
```

Only **~300MB RAM** required — a 1GB VPS runs it smoothly.

---

## 2. Core Service Usage Guide

### 2.1 S3 — Object Storage

Create a bucket and upload files:

```bash
# Create bucket
aws --endpoint-url=http://localhost:4566 s3 mb s3://my-bucket

# Upload file
aws --endpoint-url=http://localhost:4566 s3 cp ./report.pdf s3://my-bucket/docs/

# List files
aws --endpoint-url=http://localhost:4566 s3 ls s3://my-bucket/docs/

# Generate pre-signed URL (7 days)
aws --endpoint-url=http://localhost:4566 s3 presign s3://my-bucket/docs/report.pdf --expires-in 604800
```

Python SDK integration:

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

# Create bucket
s3.create_bucket(Bucket='my-app-data')

# Upload file
s3.put_object(Bucket='my-app-data', Key='config.json', Body=b'{"debug": false}')

# Download file
response = s3.get_object(Bucket='my-app-data', Key='config.json')
print(response['Body'].read().decode())
```

### 2.2 Lambda — Serverless Functions

Create a Lambda function:

```bash
# Prepare function code
mkdir -p /tmp/lambda-handler
cat > /tmp/lambda-handler/index.py << 'EOF'
import json

def handler(event, context):
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Hello from Lambda! Received: {event}'
        })
    }
EOF

# Package the function
cd /tmp/lambda-handler && zip -r function.zip .

# Create the function
aws --endpoint-url=http://localhost:4566 lambda create-function \
  --function-name hello-world \
  --runtime python3.11 \
  --role arn:aws:iam::000000000000:role/my-role \
  --handler index.handler \
  --zip-file fileb:///tmp/lambda-handler/function.zip

# Invoke the function
aws --endpoint-url=http://localhost:4566 lambda invoke \
  --function-name hello-world \
  --payload '{"key": "value"}' \
  /tmp/response.json

cat /tmp/response.json
```

### 2.3 DynamoDB — Key-Value Database

```bash
# Create table
aws --endpoint-url=http://localhost:4566 dynamodb create-table \
  --table-name Users \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Insert data
aws --endpoint-url=http://localhost:4566 dynamodb put-item \
  --table-name Users \
  --item '{"id":{"S":"user001"},"name":{"S":"John Doe"},"email":{"S":"john@example.com"}}'

# Query data
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name Users \
  --key '{"id":{"S":"user001"}}'

# Scan all items
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name Users
```

Python integration:

```python
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

table = dynamodb.Table('Users')

# Query
response = table.query(KeyConditionExpression=Key('id').eq('user001'))
for item in response['Items']:
    print(item)
```

### 2.4 SQS — Message Queue

```bash
# Create queue
aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name my-queue

# Get queue URL
QUEUE_URL=$(aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name my-queue --query 'QueueUrl' --output text)

# Send message
aws --endpoint-url=http://localhost:4566 sqs send-message \
  --queue-url $QUEUE_URL \
  --message-body '{"action": "process_image", "id": 123}'

# Receive message
aws --endpoint-url=http://localhost:4566 sqs receive-message \
  --queue-url $QUEUE_URL
```

### 2.5 SNS — Message Notifications

```bash
# Create topic
aws --endpoint-url=http://localhost:4566 sns create-topic \
  --name notifications

# Subscribe (using SQS as endpoint)
TOPIC_ARN=$(aws --endpoint-url=http://localhost:4566 sns list-topics --query 'Topics[0].TopicArn' --output text)
aws --endpoint-url=http://localhost:4566 sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol sqs \
  --notification-endpoint $QUEUE_URL

# Publish message
aws --endpoint-url=http://localhost:4566 sns publish \
  --topic-arn $TOPIC_ARN \
  --message 'System alert: disk usage exceeded 80%'
```

---

## 3. Complete Project: S3 + Lambda + DynamoDB Event-Driven Architecture

### 3.1 Scenario

User uploads a photo to S3 → triggers Lambda processing → metadata written to DynamoDB → notification sent via SNS.

### 3.2 Infrastructure Code

```yaml
# docker-compose.yml (full configuration)
services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"
      - "4510-4559:4510-4559"
    environment:
      - SERVICES=s3,lambda,dynamodb,sns,sqs,sts,iam,events
      - EDGE_PORT=4566
      - PERSISTENCE=1
      - AWS_DEFAULT_REGION=us-east-1
      - LAMBDA_EXECUTOR=local
    volumes:
      - ./localstack-data:/var/lib/localstack
      - /var/run/docker.sock:/var/run/docker.sock
```

### 3.3 Python Initialization Script

```python
#!/usr/bin/env python3
"""LocalStack infrastructure initialization script"""
import boto3
import json
from botocore.config import Config

config = Config(retries={'max_attempts': 3})
client = boto3.client(
    's3',
    endpoint_url='http://localhost:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    config=config
)
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url='http://localhost:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    config=config
)
lambda_client = boto3.client(
    'lambda',
    endpoint_url='http://localhost:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    config=config
)
sns = boto3.client(
    'sns',
    endpoint_url='http://localhost:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test',
    config=config
)

print("🚀 Initializing LocalStack infrastructure...")

# 1. Create S3 bucket
print("📦 Creating S3 bucket...")
client.create_bucket(Bucket='user-uploads')
client.put_bucket_versioning(
    Bucket='user-uploads',
    VersioningConfiguration={'Status': 'Enabled'}
)

# 2. Create DynamoDB table
print("🗄️  Creating DynamoDB table...")
table = dynamodb.create_table(
    TableName='photo_metadata',
    KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
    AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
    BillingMode='PAY_PER_REQUEST'
)
table.wait_until_exists()

# 3. Create SNS topic
print("📢 Creating SNS topic...")
topic = sns.create_topic(Name='upload-notifications')
topic_arn = topic['TopicArn']

# 4. Create Lambda function
print("⚡ Creating Lambda function...")
lambda_code = '''
import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['METADATA_TABLE'])

def handler(event, context):
    for record in event.get('Records', []):
        s3_event = record.get('S3', {})
        bucket = s3_event.get('bucket', {}).get('name', '')
        key = s3_event.get('object', {}).get('key', '')
        
        table.put_item(Item={
            'id': f"{bucket}/{key}",
            'bucket': bucket,
            'key': key,
            'size': s3_event.get('size', 0),
            'uploaded_at': s3_event.get('time', '')
        })
        
        print(f"✅ Processed: {bucket}/{key}")
    
    return {'statusCode': 200}
'''

import zipfile
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    code_path = os.path.join(tmpdir, 'function.zip')
    with open(os.path.join(tmpdir, 'index.py'), 'w') as f:
        f.write(lambda_code)
    with zipfile.ZipFile(code_path, 'w') as zf:
        zf.write(os.path.join(tmpdir, 'index.py'), 'index.py')
    
    with open(code_path, 'rb') as f:
        zip_content = f.read()
    
    lambda_client.create_function(
        FunctionName='photo-processor',
        Runtime='python3.11',
        Role='arn:aws:iam::000000000000:role/lambda-role',
        Handler='index.handler',
        Code={'ZipFile': zip_content},
        Timeout=30,
        MemorySize=256,
        Environment={
            'Variables': {
                'METADATA_TABLE': 'photo_metadata'
            }
        }
    )

# 5. Configure S3 event notification
print("🔗 Configuring S3 event notification...")
lambda_client.create_event_source_mapping(
    EventSourceArn='arn:aws:s3:::user-uploads',
    FunctionName='photo-processor',
    FilteringCriteria={
        'Rules': [{
            'Name': 'prefix',
            'Value': 'photos/'
        }]
    }
)

print("✅ Infrastructure initialization complete!")
print(f"   S3: http://localhost:4566 (bucket: user-uploads)")
print(f"   DynamoDB: photo_metadata table ready")
print(f"   Lambda: photo-processor deployed")
```

Run initialization:

```bash
python3 init_infrastructure.py
```

### 3.4 Test Upload

```python
import boto3

# Upload test file
s3 = boto3.client('s3',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

with open('test-photo.jpg', 'rb') as f:
    s3.put_object(Bucket='user-uploads', Key='photos/test-photo.jpg', Body=f.read())

# Verify DynamoDB record
dynamodb = boto3.resource('dynamodb',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)
table = dynamodb.Table('photo_metadata')
response = table.scan()
print(f"Total {response['Count']} records")
for item in response['Items']:
    print(item)
```

---

## 4. Nginx Reverse Proxy + HTTPS

To allow team members to access LocalStack via a domain name, configure Nginx reverse proxy:

```nginx
server {
    listen 80;
    server_name localstack.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name localstack.yourdomain.com;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:4566;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

After deployment, configure the AWS SDK:

```python
s3 = boto3.client(
    's3',
    endpoint_url='https://localstack.yourdomain.com',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)
```

---

## 5. Cost Analysis

### Local Development vs LocalStack on VPS

| Item | Pure Local Dev | LocalStack on VPS | Real AWS |
|------|---------------|-------------------|----------|
| S3 Storage (10GB) | Local disk | VPS disk | ~$0.23/month |
| Lambda Invocations (100K/month) | Need local simulation | VPS runs it | ~$0.20/month |
| DynamoDB (10GB) | Local SQLite | VPS storage | ~$2.50/month |
| API Gateway (emulated) | None | LocalStack emulates | ~$3.50/month |
| **Monthly Total** | **$0** | **~$5-10 (VPS)** | **~$6+/month** |

**Core value proposition**: With a single $5/month VPS, you get a development and testing experience nearly identical to the AWS production environment, without any billing surprises.

---

## 6. Frequently Asked Questions

### Q: Will LocalStack data be lost?

With `PERSISTENCE=1` enabled, data is persisted to the `./localstack-data` directory. Regularly back up this directory.

### Q: How do I reset all data?

```bash
docker compose down
rm -rf localstack-data
docker compose up -d
```

### Q: How many AWS services can LocalStack emulate?

As of 2026, LocalStack Pro supports **200+ AWS services**, while the community edition supports core 50+ services. This covers mainstream services including S3, Lambda, DynamoDB, EC2, RDS, ECS, and Kinesis.

### Q: Can I mix LocalStack with real AWS services?

Yes! LocalStack supports a **Local + External Services** mode. Add to `docker-compose.yml`:

```yaml
environment:
  - DEBUG=1
  - EXTRA_CORS_ALLOWED_ORIGINS=*
```

Then specify which services route to real AWS and which to LocalStack via environment variables.

---

## Summary

LocalStack is one of the most underrated development tools on a VPS. It enables you to:

- ✅ **Zero-cost** develop and test AWS applications
- ✅ Work **fully offline**, no AWS network dependency
- ✅ **CI/CD integration**, automated tests no longer consume cloud resources
- ✅ **Team collaboration**, unified infrastructure definition files

A single `docker-compose.yml` and a few minutes are all it takes to set up a development and testing platform consistent with your production environment. Stop paying for test environments on AWS — your VPS is the cheapest development cloud platform you'll ever need.
