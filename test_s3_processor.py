import boto3
import pandas as pd
import io
import pytest
import os
import tempfile
from moto import mock_s3
from s3_data_processor import S3DataProcessor


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for boto3."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials):
    with mock_s3():
        conn = boto3.client("s3", region_name="us-east-1")
        yield conn


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


def test_list_s3_objects(setup_s3_buckets, monkeypatch):
    """Test listing objects from S3."""
    input_bucket, output_bucket = setup_s3_buckets
    
    # Disable AWS Data Wrangler for this test
    monkeypatch.setenv("USE_WRANGLER", "False")
    
    processor = S3DataProcessor(
        input_bucket=input_bucket,
        output_bucket=output_bucket,
        prefix="test/data/",
        use_wrangler=False
    )
    
    objects = processor.list_s3_objects()
    
    assert len(objects) == 3
    assert all(obj["Key"].startswith("test/data/") for obj in objects)


def test_read_csv_to_dataframe(setup_s3_buckets, monkeypatch):
    """Test reading a CSV file from S3 into a DataFrame."""
    input_bucket, output_bucket = setup_s3_buckets
    
    # Disable AWS Data Wrangler for this test
    monkeypatch.setenv("USE_WRANGLER", "False")
    
    processor = S3DataProcessor(
        input_bucket=input_bucket,
        output_bucket=output_bucket,
        prefix="test/data/",
        use_wrangler=False
    )
    
    df = processor.read_csv_to_dataframe(input_bucket, "test/data/file0.csv")
    
    assert isinstance(df, pd.DataFrame)
    assert df.shape == (3, 3)
    assert list(df.columns) == ["id", "name", "value"]
    assert df["id"].tolist() == ["1", "2", "3"]


def test_process_file(setup_s3_buckets, monkeypatch):
    """Test processing a single file."""
    input_bucket, output_bucket = setup_s3_buckets
    
    # Disable AWS Data Wrangler for this test
    monkeypatch.setenv("USE_WRANGLER", "False")
    
    processor = S3DataProcessor(
        input_bucket=input_bucket,
        output_bucket=output_bucket,
        prefix="test/data/",
        use_wrangler=False
    )
    
    # Get a test object
    objects = processor.list_s3_objects()
    test_obj = objects[0]
    
    # Process the file
    key, elapsed = processor.process_file(test_obj)
    
    # Check the output files were created
    s3_client = boto3.client("s3")
    
    # Check Parquet file
    parquet_key = test_obj["Key"].replace(".csv", ".parquet").replace("test/data/", "processed/")
    response = s3_client.list_objects_v2(
        Bucket=output_bucket,
        Prefix=parquet_key
    )
    assert "Contents" in response
    
    # Check Avro file
    avro_key = test_obj["Key"].replace(".csv", ".avro").replace("test/data/", "processed/")
    response = s3_client.list_objects_v2(
        Bucket=output_bucket,
        Prefix=avro_key
    )
    assert "Contents" in response


def test_process_all_files(setup_s3_buckets, monkeypatch):
    """Test processing all files in the bucket."""
    input_bucket, output_bucket = setup_s3_buckets
    
    # Disable AWS Data Wrangler for this test
    monkeypatch.setenv("USE_WRANGLER", "False")
    
    processor = S3DataProcessor(
        input_bucket=input_bucket,
        output_bucket=output_bucket,
        prefix="test/data/",
        use_wrangler=False,
        max_workers=2
    )
    
    results = processor.process_all_files()
    
    assert len(results) == 3
    assert all(elapsed > 0 for elapsed in results.values())
    
    # Check all output files were created
    s3_client = boto3.client("s3")
    
    response = s3_client.list_objects_v2(
        Bucket=output_bucket,
        Prefix="processed/"
    )
    
    assert "Contents" in response
    assert len(response["Contents"]) == 6  # 3 files x 2 formats 