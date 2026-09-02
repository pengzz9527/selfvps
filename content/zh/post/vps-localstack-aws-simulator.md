---
title: "在 VPS 上部署 LocalStack：本地 AWS 云服务模拟器完整指南"
date: 2026-09-02
description: "不用花一分钱 AWS 费用，在你的 VPS 上部署 LocalStack，本地模拟 S3、Lambda、DynamoDB、SQS 等 200+ 项 AWS 服务，开发测试零成本。"
tags: ["LocalStack", "AWS", "VPS", "开发环境", "Docker", "S3", "Lambda", "自托管", "省钱"]
categories: ["云省钱"]
image: "/images/posts/vps-localstack-aws-simulator/featured.png"
draft: false
---

## 引言

你是否遇到过这样的场景：

- 开发了一个调用 S3 上传文件的应用，部署时才发现 AWS Access Key 配错了；
- 想在本地测试 Lambda 函数，但每次都要推送到云端才能运行；
- 想测试 DynamoDB 查询性能，却担心测试数据产生真实费用；
- 团队 CI/CD 流水线依赖 AWS 服务，每次测试都要消耗预算。

**这些问题，LocalStack 都能解决。**

LocalStack 是一款开源的本地云开发测试框架，它在你本地或 VPS 上模拟了 **200+ 项 AWS 服务**，包括 S3、Lambda、DynamoDB、SQS、SNS、Kinesis、ECS、RDS 等等。你的应用程序完全不需要修改代码，只需把 AWS SDK 的端点指向 LocalStack，就能在本地完成全部开发和测试。

本文将带你从零开始在 VPS 上部署 LocalStack，包括 Docker Compose 配置、常用服务使用、与 AWS SDK 集成、以及实际项目应用案例。

---

## 为什么在 VPS 上跑 LocalStack？

| 方案 | 成本 | 网络延迟 | 持久性 | 团队协作 |
|------|------|----------|--------|----------|
| 本地电脑跑 LocalStack | 零 | 零 | 本地磁盘 | 需各自部署 |
| AWS Local (付费) | 高（按实例计费） | 低 | 云端 | 容易共享 |
| **VPS 上跑 LocalStack** | **低（固定月费）** | **低** | **云服务器持久存储** | **团队成员共享同一实例** |

VPS 方案的核心优势：**一台低配 VPS（2C2G）即可运行，团队成员通过同一端点访问，开发和测试环境完全一致。**

---

## 1. 快速启动：Docker Compose 一键部署

### 1.1 基础版（推荐）

创建 `docker-compose.yml`：

```yaml
services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"          # LocalStack 主端口
      - "4510-4559:4510-4559" # 附加端口范围
    environment:
      - SERVICES=s3,lambda,dynamodb,sns,sqs,sts,kinesis,ecr,iam,secretsmanager,apigateway,events,redshift,rds,cloudformation,cloudwatch,firelens,es,kms,ssm,stepfunctions,codepipeline,glue,config,transcribe,neptune,sagemaker
      - EDGE_PORT=4566
      - PERSISTENCE=1         # 启用数据持久化
      - AWS_DEFAULT_REGION=us-east-1
    volumes:
      - ./localstack-data:/var/lib/localstack  # 数据持久化
      - /var/run/docker.sock:/var/run/docker.sock  # 让 LocalStack 管理容器（Lambda 需要）
    networks:
      - localstack-net

networks:
  localstack-net:
    driver: bridge
```

启动服务：

```bash
docker compose up -d
```

验证部署：

```bash
curl http://localhost:4566/_localstack/health
```

返回示例：

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

### 1.2 精简版（节省资源）

如果只需要常用服务，可以精简配置：

```yaml
environment:
  - SERVICES=s3,lambda,dynamodb,sqs,sns,sts
  - EDGE_PORT=4566
  - PERSISTENCE=1
  - AWS_DEFAULT_REGION=us-east-1
```

仅需 **~300MB 内存**，1GB 内存的 VPS 即可流畅运行。

---

## 2. 核心服务使用指南

### 2.1 S3 — 对象存储

创建存储桶并上传文件：

```bash
# 创建存储桶
aws --endpoint-url=http://localhost:4566 s3 mb s3://my-bucket

# 上传文件
aws --endpoint-url=http://localhost:4566 s3 cp ./report.pdf s3://my-bucket/docs/

# 列出文件
aws --endpoint-url=http://localhost:4566 s3 ls s3://my-bucket/docs/

# 生成预签名 URL（7 天有效）
aws --endpoint-url=http://localhost:4566 s3 presign s3://my-bucket/docs/report.pdf --expires-in 604800
```

Python SDK 集成：

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

# 创建 bucket
s3.create_bucket(Bucket='my-app-data')

# 上传文件
s3.put_object(Bucket='my-app-data', Key='config.json', Body=b'{"debug": false}')

# 下载文件
response = s3.get_object(Bucket='my-app-data', Key='config.json')
print(response['Body'].read().decode())
```

### 2.2 Lambda — 无服务器函数

创建 Lambda 函数：

```bash
# 准备函数代码
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

# 打包函数
cd /tmp/lambda-handler && zip -r function.zip .

# 创建函数
aws --endpoint-url=http://localhost:4566 lambda create-function \
  --function-name hello-world \
  --runtime python3.11 \
  --role arn:aws:iam::000000000000:role/my-role \
  --handler index.handler \
  --zip-file fileb:///tmp/lambda-handler/function.zip

# 调用函数
aws --endpoint-url=http://localhost:4566 lambda invoke \
  --function-name hello-world \
  --payload '{"key": "value"}' \
  /tmp/response.json

cat /tmp/response.json
```

### 2.3 DynamoDB — 键值数据库

```bash
# 创建表
aws --endpoint-url=http://localhost:4566 dynamodb create-table \
  --table-name Users \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# 插入数据
aws --endpoint-url=http://localhost:4566 dynamodb put-item \
  --table-name Users \
  --item '{"id":{"S":"user001"},"name":{"S":"张三"},"email":{"S":"zhangsan@example.com"}}'

# 查询数据
aws --endpoint-url=http://localhost:4566 dynamodb get-item \
  --table-name Users \
  --key '{"id":{"S":"user001"}}'

# 列表查询
aws --endpoint-url=http://localhost:4566 dynamodb scan --table-name Users
```

Python 集成：

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

# 查询
response = table.query(KeyConditionExpression=Key('id').eq('user001'))
for item in response['Items']:
    print(item)
```

### 2.4 SQS — 消息队列

```bash
# 创建队列
aws --endpoint-url=http://localhost:4566 sqs create-queue \
  --queue-name my-queue

# 获取队列 URL
QUEUE_URL=$(aws --endpoint-url=http://localhost:4566 sqs get-queue-url \
  --queue-name my-queue --query 'QueueUrl' --output text)

# 发送消息
aws --endpoint-url=http://localhost:4566 sqs send-message \
  --queue-url $QUEUE_URL \
  --message-body '{"action": "process_image", "id": 123}'

# 接收消息
aws --endpoint-url=http://localhost:4566 sqs receive-message \
  --queue-url $QUEUE_URL
```

### 2.5 SNS — 消息通知

```bash
# 创建主题
aws --endpoint-url=http://localhost:4566 sns create-topic \
  --name notifications

# 订阅（使用 SQS 作为端点）
TOPIC_ARN=$(aws --endpoint-url=http://localhost:4566 sns list-topics --query 'Topics[0].TopicArn' --output text)
aws --endpoint-url=http://localhost:4566 sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol sqs \
  --notification-endpoint $QUEUE_URL

# 发布消息
aws --endpoint-url=http://localhost:4566 sns publish \
  --topic-arn $TOPIC_ARN \
  --message '系统告警：磁盘使用率超过 80%'
```

---

## 3. 完整项目实战：S3 + Lambda + DynamoDB 事件驱动架构

### 3.1 场景描述

用户上传照片到 S3 → 触发 Lambda 处理 → 元数据写入 DynamoDB → 发送通知到 SNS。

### 3.2 基础设施代码

```yaml
# docker-compose.yml（完整配置）
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

### 3.3 Python 初始化脚本

```python
#!/usr/bin/env python3
"""LocalStack 基础设施初始化脚本"""
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

print("🚀 初始化 LocalStack 基础设施...")

# 1. 创建 S3 存储桶
print("📦 创建 S3 存储桶...")
client.create_bucket(Bucket='user-uploads')
client.put_bucket_versioning(
    Bucket='user-uploads',
    VersioningConfiguration={'Status': 'Enabled'}
)

# 2. 创建 DynamoDB 表
print("🗄️ 创建 DynamoDB 表...")
table = dynamodb.create_table(
    TableName='photo_metadata',
    KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
    AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
    BillingMode='PAY_PER_REQUEST'
)
table.wait_until_exists()

# 3. 创建 SNS 主题
print("📢 创建 SNS 主题...")
topic = sns.create_topic(Name='upload-notifications')
topic_arn = topic['TopicArn']

# 4. 创建 Lambda 函数
print("⚡ 创建 Lambda 函数...")
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
        
        # 写入 DynamoDB
        table.put_item(Item={
            'id': f"{bucket}/{key}",
            'bucket': bucket,
            'key': key,
            'size': s3_event.get('size', 0),
            'uploaded_at': s3_event.get('time', '')
        })
        
        print(f"✅ 处理完成: {bucket}/{key}")
    
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

# 5. 配置 S3 事件通知
print("🔗 配置 S3 事件通知...")
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

print("✅ 基础设施初始化完成！")
print(f"   S3: http://localhost:4566(bucket: user-uploads)")
print(f"   DynamoDB: photo_metadata 表已就绪")
print(f"   Lambda: photo-processor 已部署")
```

运行初始化：

```bash
python3 init_infrastructure.py
```

### 3.4 测试上传

```python
import boto3

# 上传测试文件
s3 = boto3.client('s3',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)

with open('test-photo.jpg', 'rb') as f:
    s3.put_object(Bucket='user-uploads', Key='photos/test-photo.jpg', Body=f.read())

# 验证 DynamoDB 记录
dynamodb = boto3.resource('dynamodb',
    endpoint_url='http://YOUR_VPS_IP:4566',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)
table = dynamodb.Table('photo_metadata')
response = table.scan()
print(f"共 {response['Count']} 条记录")
for item in response['Items']:
    print(item)
```

---

## 4. 使用 Nginx 反向代理 + HTTPS

为了让团队通过域名访问 LocalStack，配置 Nginx 反向代理：

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

        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

部署后，AWS SDK 配置：

```python
s3 = boto3.client(
    's3',
    endpoint_url='https://localstack.yourdomain.com',
    aws_access_key_id='test',
    aws_secret_access_key='test'
)
```

---

## 5. 成本分析

### 本地开发 vs LocalStack on VPS

| 项目 | 纯本地开发 | LocalStack on VPS | AWS 真实环境 |
|------|-----------|-------------------|-------------|
| S3 存储（10GB） | 本地磁盘 | VPS 磁盘 | ~$0.23/月 |
| Lambda 执行（10万次/月） | 需本地模拟 | VPS 运行 | ~$0.20/月 |
| DynamoDB（10GB） | 本地 SQLite | VPS 存储 | ~$2.50/月 |
| API Gateway（模拟） | 无 | LocalStack 模拟 | ~$3.50/月 |
| 月度总成本 | $0 | **~$5-10（VPS）** | **~$6+/月** |

**核心价值**：用一台 $5/月的 VPS，获得与 AWS 生产环境几乎一致的开发测试体验，无需担心账单惊喜。

---

## 6. 常见问题

### Q: LocalStack 数据会丢失吗？

启用 `PERSISTENCE=1` 后，数据持久化到 `./localstack-data` 目录。定期备份该目录即可。

### Q: 如何重置所有数据？

```bash
docker compose down
rm -rf localstack-data
docker compose up -d
```

### Q: LocalStack 可以模拟多少 AWS 服务？

截至 2026 年，LocalStack Pro 支持 **200+ 项** AWS 服务，社区版支持核心 50+ 项。覆盖 S3、Lambda、DynamoDB、EC2、RDS、ECS、Kinesis 等主流服务。

### Q: 能否直接连接真实的 AWS 服务混合使用？

可以！LocalStack 支持 **Local + External Services** 模式。在 `docker-compose.yml` 中添加：

```yaml
environment:
  - DEBUG=1
  - EXTRA_CORS_ALLOWED_ORIGINS=*
```

然后通过环境变量指定哪些服务走真实 AWS，哪些走 LocalStack。

---

## 总结

LocalStack 是 VPS 上最被低估的开发神器之一。它让你：

- ✅ **零成本**开发和测试 AWS 应用
- ✅ **完全离线**环境下工作，不依赖 AWS 网络
- ✅ **CI/CD 集成**，自动化测试不再消耗云资源
- ✅ **团队协作**，统一的基础设施定义文件

一套 `docker-compose.yml`，几分钟内就能搭好与生产环境一致的开发测试平台。别再为测试环境花 AWS 的钱了——你的 VPS 就是最便宜的开发云平台。
