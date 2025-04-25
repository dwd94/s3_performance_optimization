# Infrastructure Setup Guide

This guide provides instructions for setting up the optimized S3 data processing solution in AWS.

## Option 1: AWS Lambda Deployment (Recommended)

### 1. Create Lambda Deployment Package

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create deployment package
mkdir package
pip install --target ./package -r requirements.txt
cd package
zip -r ../lambda_function.zip .
cd ..
zip -g lambda_function.zip s3_data_processor.py
```

### 2. Create Lambda Function

1. Go to AWS Lambda Console
2. Click "Create function"
3. Select "Author from scratch"
4. Enter function name (e.g., `s3-csv-processor`)
5. Runtime: Python 3.9+
6. Architecture: x86_64
7. Click "Create function"

### 3. Configure Lambda Function

1. Upload the `lambda_function.zip` package
2. Set handler to `s3_data_processor.lambda_handler`
3. Configure environment variables:
   - `INPUT_BUCKET`: Your input bucket name
   - `OUTPUT_BUCKET`: Your output bucket name
   - `PREFIX`: Path prefix for CSV files
   - `MAX_WORKERS`: Number of concurrent workers (e.g., 20)
   - `USE_WRANGLER`: Set to "True" to use AWS Data Wrangler

4. Adjust memory and timeout:
   - Memory: 2048 MB (minimum recommended)
   - Timeout: 5 minutes

5. Add IAM permissions:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:ListBucket",
                   "s3:GetObject",
                   "s3:PutObject"
               ],
               "Resource": [
                   "arn:aws:s3:::your-input-bucket*",
                   "arn:aws:s3:::your-output-bucket*"
               ]
           }
       ]
   }
   ```

### 4. Set Up Triggers

#### Option A: S3 Event Trigger
1. Add trigger: S3
2. Bucket: Your input bucket
3. Event type: All object create events
4. Prefix: Your desired prefix (e.g., "incoming/")

#### Option B: EventBridge Schedule
1. Add trigger: EventBridge (CloudWatch Events)
2. Create a new rule
3. Schedule expression: `rate(5 minutes)` or `cron(0/15 * * * ? *)`

## Option 2: AWS Fargate Deployment

### 1. Create ECR Repository

```bash
aws ecr create-repository --repository-name s3-csv-processor
```

### 2. Create Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY s3_data_processor.py .

CMD ["python", "s3_data_processor.py"]
```

### 3. Build and Push Docker Image

```bash
# Build image
docker build -t s3-csv-processor .

# Tag and push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<region>.amazonaws.com
docker tag s3-csv-processor:latest <your-account-id>.dkr.ecr.<region>.amazonaws.com/s3-csv-processor:latest
docker push <your-account-id>.dkr.ecr.<region>.amazonaws.com/s3-csv-processor:latest
```

### 4. Create ECS Task Definition

1. Go to ECS Console
2. Create a task definition:
   - Type: Fargate
   - Name: s3-csv-processor
   - Task role: Create with S3 permissions
   - Task memory: 2GB
   - Task CPU: 1 vCPU
   - Container:
     - Name: s3-csv-processor
     - Image: <your-account-id>.dkr.ecr.<region>.amazonaws.com/s3-csv-processor:latest
     - Environment variables:
       - `INPUT_BUCKET`: Your input bucket
       - `OUTPUT_BUCKET`: Your output bucket
       - `PREFIX`: Your prefix
       - `MAX_WORKERS`: 20
       - `USE_WRANGLER`: "True"

### 5. Create Scheduled Task

1. Use EventBridge to schedule the Fargate task
2. Create a new rule with a schedule pattern
3. Select the ECS task as the target

## Option 3: EC2 Deployment

### 1. Launch EC2 Instance

1. Launch a t3.medium or larger instance
2. AMI: Amazon Linux 2 or Ubuntu
3. Security Group: Allow SSH access

### 2. Install Dependencies

```bash
# Update system packages
sudo yum update -y  # Amazon Linux
# or
sudo apt update && sudo apt upgrade -y  # Ubuntu

# Install Python and git
sudo yum install -y python3 python3-pip git  # Amazon Linux
# or
sudo apt install -y python3 python3-pip git  # Ubuntu

# Clone repository (if using git) or copy files
git clone <your-repo-url>
# or
mkdir -p ~/s3-processor
# Copy files to the directory

# Install dependencies
pip3 install -r requirements.txt
```

### 3. Configure AWS Credentials

```bash
aws configure
# Enter your AWS credentials and region
```

### 4. Create Systemd Service

```bash
sudo nano /etc/systemd/system/s3processor.service
```

Add the following content:

```
[Unit]
Description=S3 CSV Processor
After=network.target

[Service]
User=ec2-user  # or ubuntu for Ubuntu
WorkingDirectory=/home/ec2-user/s3-processor
ExecStart=/usr/bin/python3 /home/ec2-user/s3-processor/s3_data_processor.py
Restart=on-failure
Environment=INPUT_BUCKET=your-input-bucket
Environment=OUTPUT_BUCKET=your-output-bucket
Environment=PREFIX=your-prefix
Environment=MAX_WORKERS=20
Environment=USE_WRANGLER=True

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable s3processor
sudo systemctl start s3processor
sudo systemctl status s3processor
```

## Monitoring Setup

### CloudWatch Metrics and Alarms

1. Create custom metrics for:
   - Total files processed
   - Processing time per file
   - Error rate

2. Create CloudWatch Alarms for:
   - High error rate (>5%)
   - Long processing durations
   - Lambda/Task failures

### X-Ray Tracing (Lambda and Fargate)

1. Enable X-Ray active tracing
2. Add the AWS X-Ray SDK to requirements.txt
3. Update code to include X-Ray tracing segments 