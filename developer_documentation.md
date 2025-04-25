# S3 Data Processing Solution - Developer Documentation

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Structure](#code-structure)
3. [Core Components](#core-components)
4. [Technical Implementation](#technical-implementation)
5. [Performance Optimization Techniques](#performance-optimization-techniques)
6. [Deployment Guide](#deployment-guide)
7. [Testing](#testing)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)
10. [Future Enhancements](#future-enhancements)

## Architecture Overview

The S3 Data Processor is designed to efficiently convert CSV files stored in AWS S3 to Parquet and Avro formats. The solution follows a modular, object-oriented architecture that focuses on parallel processing, optimized I/O operations, and robust error handling.

### System Flow

```
                                   ┌─────────────────┐
                                   │                 │
                                   │  AWS S3 Bucket  │
                                   │   (Input CSV)   │
                                   │                 │
                                   └────────┬────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌────────────────┐     ┌───────────────────┐    ┌──────────────┐  │
│  │                │     │                   │    │              │  │
│  │  List Objects  │────▶│  Thread Pool     │───▶│  Process     │  │
│  │                │     │  Executor        │    │  Individual  │  │
│  └────────────────┘     │                   │    │  Files      │  │
│                         └───────────────────┘    │              │  │
│                                                  └─────┬────────┘  │
│                                                        │           │
│                                                        ▼           │
│                         ┌─────────────────────────────────────┐    │
│                         │                                     │    │
│                         │     Parallel Format Conversion      │    │
│                         │                                     │    │
│                         │  ┌─────────────┐  ┌─────────────┐  │    │
│                         │  │             │  │             │  │    │
│                         │  │  To Parquet │  │  To Avro    │  │    │
│                         │  │             │  │             │  │    │
│                         │  └─────────────┘  └─────────────┘  │    │
│                         │                                     │    │
│                         └─────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
                                   ┌─────────────────┐
                                   │                 │
                                   │  AWS S3 Bucket  │
                                   │  (Output Files) │
                                   │                 │
                                   └─────────────────┘
```

### Key Components

1. **S3 Data Processor Core**: The main processing engine responsible for file operations
2. **Lambda Handler**: Integration with AWS Lambda for serverless execution
3. **ThreadPoolExecutor**: Manages parallel execution of file processing tasks
4. **AWS Data Wrangler Integration**: Optimized S3 I/O operations
5. **Error Handling & Logging**: Comprehensive error management system

## Code Structure

```
s3-data-processor/
├── s3_data_processor.py    # Core processing class
├── lambda_handler.py       # AWS Lambda integration
├── requirements.txt        # Dependencies
├── test_s3_processor.py    # Unit tests
├── README.md               # Project overview
├── performance_comparison.md # Performance metrics
└── infra_setup.md         # Infrastructure setup guide
```

## Core Components

### S3DataProcessor Class

The `S3DataProcessor` class is the main component responsible for processing S3 files. It provides the following functionality:

1. **Initialization**:
   - Configure S3 client and resources
   - Set up processing parameters
   - Initialize caching

2. **File Listing and Discovery**:
   - List objects in S3 with pagination
   - Filter by prefix

3. **File Processing**:
   - Read CSV files from S3
   - Convert to Parquet and Avro formats
   - Write processed files back to S3

4. **Parallel Execution**:
   - Multi-file processing with ThreadPoolExecutor
   - Per-file parallel format conversion

5. **Caching and Optimization**:
   - LRU cache for frequent file operations
   - Connection pooling
   - AWS Data Wrangler integration

### Lambda Handler

The `lambda_handler.py` module provides AWS Lambda integration with:

1. **Event Handling**:
   - S3 event notifications
   - EventBridge scheduled events
   - Direct invocation

2. **Environment Configuration**:
   - Read environment variables
   - Configure processor parameters

3. **Results Processing**:
   - Calculate performance statistics
   - Format response

## Technical Implementation

### S3 Object Listing

```python
def list_s3_objects(self) -> List[Dict[str, Any]]:
    """List all objects under the prefix in the input bucket."""
    try:
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.input_bucket, Prefix=self.prefix)
        
        all_objects = []
        for page in pages:
            if "Contents" in page:
                all_objects.extend(page["Contents"])
        
        if not all_objects:
            logger.warning(f"⚠️ No files found at s3://{self.input_bucket}/{self.prefix}")
            return []
        
        logger.info(f"Found {len(all_objects)} files to process")
        return all_objects
    except Exception as e:
        logger.error(f"❌ Error listing objects: {e}")
        return []
```

### S3 File Reading with Caching

```python
@lru_cache(maxsize=128)
def _read_s3_file_cached(self, bucket: str, key: str) -> bytes:
    """Read an S3 file with caching for repeated access."""
    obj = self.s3_client.get_object(Bucket=bucket, Key=key)
    return obj['Body'].read()

def read_s3_file(self, bucket: str, key: str) -> bytes:
    """Read an S3 file with optional caching."""
    start_time = time.time()
    
    if self.cache_size > 0:
        data = self._read_s3_file_cached(bucket, key)
    else:
        obj = self.s3_client.get_object(Bucket=bucket, Key=key)
        data = obj['Body'].read()
    
    elapsed = time.time() - start_time
    logger.debug(f"S3 read took {elapsed:.4f} seconds for {key}")
    return data
```

### CSV to Parquet/Avro Conversion

```python
def read_csv_to_dataframe(self, bucket: str, key: str) -> pd.DataFrame:
    """Read a CSV file from S3 into a pandas DataFrame."""
    start_time = time.time()
    
    if self.use_wrangler:
        # Use AWS Data Wrangler for optimized S3 CSV reading
        df = wr.s3.read_csv(f"s3://{bucket}/{key}")
    else:
        # Standard pandas read
        data = self.read_s3_file(bucket, key)
        df = pd.read_csv(io.BytesIO(data))
    
    elapsed = time.time() - start_time
    logger.info(f"✅ CSV file read from s3://{bucket}/{key} in {elapsed:.6f}s")
    return df
```

### Parallel File Processing

```python
def process_all_files(self) -> Dict[str, float]:
    """Process all files in the bucket under the specified prefix."""
    objects = self.list_s3_objects()
    if not objects:
        return {}
    
    results = {}
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        future_to_key = {executor.submit(self.process_file, obj): obj["Key"] for obj in objects}
        
        for future in concurrent.futures.as_completed(future_to_key):
            key = future_to_key[future]
            try:
                file_key, elapsed = future.result()
                if elapsed > 0:
                    results[file_key] = elapsed
            except Exception as e:
                logger.error(f"❌ Error in worker thread for {key}: {e}")
    
    total_time = time.time() - start_time
    logger.info(f"✅ Processed {len(results)} files in {total_time:.2f} seconds")
    
    return results
```

### Parallel Format Conversion

```python
def process_file(self, obj: Dict[str, Any]) -> Tuple[str, float]:
    """Process a single S3 object, converting to Parquet and Avro."""
    key = obj["Key"]
    file_name = key.split("/")[-1]
    base_name = os.path.splitext(file_name)[0]
    
    start_time = time.time()
    logger.info(f"🔄 Processing file: {key}")
    
    try:
        # Read the CSV file
        df = self.read_csv_to_dataframe(self.input_bucket, key)
        
        # Define output keys
        parquet_key = key.replace(".csv", ".parquet").replace(self.prefix, "processed/")
        avro_key = key.replace(".csv", ".avro").replace(self.prefix, "processed/")
        
        # Write to Parquet and Avro in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self.write_parquet_to_s3, df, self.output_bucket, parquet_key),
                executor.submit(self.write_avro_to_s3, df, self.output_bucket, avro_key)
            ]
            concurrent.futures.wait(futures)
        
        elapsed = time.time() - start_time
        return key, elapsed
    
    except Exception as e:
        logger.error(f"❌ Error processing {key}: {e}")
        return key, -1
```

## Performance Optimization Techniques

### 1. Parallel Processing

The solution uses ThreadPoolExecutor in two levels:

1. **File-level parallelism**: Process multiple files simultaneously
   ```python
   with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
       future_to_key = {executor.submit(self.process_file, obj): obj["Key"] for obj in objects}
   ```

2. **Operation-level parallelism**: Convert to multiple formats in parallel
   ```python
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
       futures = [
           executor.submit(self.write_parquet_to_s3, df, self.output_bucket, parquet_key),
           executor.submit(self.write_avro_to_s3, df, self.output_bucket, avro_key)
       ]
   ```

This approach maximizes CPU utilization and minimizes waiting time on I/O operations.

### 2. Memory Caching

The solution implements LRU caching to avoid redundant S3 reads:

```python
@lru_cache(maxsize=128)
def _read_s3_file_cached(self, bucket: str, key: str) -> bytes:
    """Read an S3 file with caching for repeated access."""
    obj = self.s3_client.get_object(Bucket=bucket, Key=key)
    return obj['Body'].read()
```

### 3. Connection Pooling

Connection pooling is used to reduce the overhead of establishing new connections:

```python
self.s3_resource = self.session.resource('s3', 
    config=boto3.config.Config(max_pool_connections=50))
```

### 4. AWS Data Wrangler Integration

AWS Data Wrangler provides optimized data transfer between pandas DataFrames and AWS services:

```python
if self.use_wrangler:
    # Use AWS Data Wrangler for optimized S3 CSV reading
    df = wr.s3.read_csv(f"s3://{bucket}/{key}")
```

### 5. Efficient Data Serialization

The solution uses PyArrow for efficient data serialization:

```python
buffer = io.BytesIO()
table = pa.Table.from_pandas(df)
pq.write_table(table, buffer, compression="snappy")
```

## Deployment Guide

### AWS Lambda Deployment

1. **Create deployment package**:

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
zip -g lambda_function.zip s3_data_processor.py lambda_handler.py
```

2. **Create Lambda function**:

- Go to AWS Lambda Console
- Create function (Author from scratch)
- Runtime: Python 3.9+
- Upload the deployment package
- Set handler to `lambda_handler.lambda_handler`

3. **Configure environment variables**:

- `INPUT_BUCKET`: S3 bucket containing input CSV files
- `OUTPUT_BUCKET`: S3 bucket for output Parquet and Avro files
- `PREFIX`: Path prefix within the input bucket
- `MAX_WORKERS`: Number of concurrent workers (e.g., 20)
- `USE_WRANGLER`: Whether to use AWS Data Wrangler (True/False)
- `CACHE_SIZE`: Size of LRU cache (e.g., 128)

4. **Set Lambda configuration**:

- Memory: 2048 MB (recommended)
- Timeout: 5 minutes
- Provisioned concurrency: 10 (for production workloads)

5. **Set up IAM permissions**:

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

### AWS Fargate Deployment

For detailed Fargate deployment instructions, refer to the `infra_setup.md` document.

## Testing

### Unit Testing

The solution includes comprehensive unit tests using pytest and moto for S3 mocking:

```python
@pytest.fixture
def setup_s3_buckets(s3_client):
    """Create mock S3 buckets and test data."""
    # Create test buckets
    s3_client.create_bucket(Bucket="test-input-bucket")
    s3_client.create_bucket(Bucket="test-output-bucket")
    
    # Create test CSV data
    csv_data = """id,name,value
1,test1,100
2,test2,200
3,test3,300
"""
    
    # Upload test files to S3
    for i in range(3):
        key = f"test/data/file{i}.csv"
        s3_client.put_object(
            Bucket="test-input-bucket",
            Key=key,
            Body=csv_data
        )
    
    return "test-input-bucket", "test-output-bucket"
```

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest test_s3_processor.py -v
```

## Monitoring

### AWS CloudWatch Metrics

The following CloudWatch metrics should be monitored:

1. **Invocation metrics**:
   - Invocation count
   - Error count
   - Duration

2. **Custom metrics** (implement using CloudWatch Logs Insights):
   - Files processed per invocation
   - Average processing time per file
   - Processing failures

### CloudWatch Alarms

Set up the following alarms:

1. **Error rate alarm**:
   - Threshold: Error rate > 5%
   - Period: 5 minutes
   - Actions: SNS notification

2. **Duration alarm**:
   - Threshold: Duration > 80% of timeout
   - Period: 5 minutes
   - Actions: SNS notification

3. **Throttling alarm**:
   - Threshold: Throttled invocations > 0
   - Period: 5 minutes
   - Actions: SNS notification + increase provisioned concurrency

### X-Ray Tracing

For detailed performance analysis, enable X-Ray tracing:

1. Enable active tracing in the Lambda configuration
2. Add AWS X-Ray SDK to requirements.txt
3. Update code to include X-Ray segment annotations

## Troubleshooting

### Common Issues

1. **Lambda timeout errors**:
   - Increase Lambda timeout
   - Increase memory allocation
   - Reduce batch size

2. **S3 rate limiting**:
   - Implement exponential backoff retry logic
   - Reduce concurrent connections

3. **Memory issues**:
   - Increase Lambda memory
   - Process files in smaller batches
   - Use streaming processing for very large files

### Debugging Tips

1. **Enable DEBUG level logging**:
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Add detailed timing logs**:
   ```python
   start_time = time.time()
   # operation
   elapsed = time.time() - start_time
   logger.debug(f"Operation took {elapsed:.6f} seconds")
   ```

3. **Monitor memory usage**:
   ```python
   import resource
   logger.debug(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024} MB")
   ```

## Future Enhancements

1. **SQS Integration**:
   - Add support for SQS queues to manage processing backlog
   - Implement dead-letter queues for failed processing

2. **Adaptive Concurrency**:
   - Dynamically adjust concurrency based on system load
   - Implement rate limiting based on S3 response times

3. **Format Customization**:
   - Add support for additional output formats
   - Allow customization of compression settings

4. **Data Validation**:
   - Implement schema validation for input CSV files
   - Add data quality checks during processing

5. **Enhanced Metrics**:
   - Implement custom CloudWatch metrics
   - Create CloudWatch dashboard for monitoring 