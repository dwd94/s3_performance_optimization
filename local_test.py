#!/usr/bin/env python3
"""
Local testing script for S3 Data Processor without requiring actual AWS resources.
This script uses moto to mock AWS S3 and simulates the data processing workflow.
"""

import os
import sys
import time
import pandas as pd
import io
import boto3
import logging
import tempfile
from moto import mock_aws
from pathlib import Path
import csv

# Adjust path to import s3_data_processor module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # Import the simplified version for local testing
    from s3_data_processor_simplified import S3DataProcessor
    print("Successfully imported S3DataProcessor from simplified version")
except ImportError:
    print("Could not import S3DataProcessor. Make sure s3_data_processor_simplified.py is in the same directory.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TEST_INPUT_BUCKET = "test-input-bucket"
TEST_OUTPUT_BUCKET = "test-output-bucket"
TEST_PREFIX = "test/data/"
NUM_TEST_FILES = 10
ROWS_PER_FILE = 1000
CSV_COLUMNS = ["id", "name", "value", "timestamp", "category", "subcategory", "status", "priority", "amount", "description"]


def generate_test_csv_data(rows=ROWS_PER_FILE):
    """Generate test CSV data with the specified number of rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    
    # Write header
    writer.writerow(CSV_COLUMNS)
    
    # Write data rows
    for i in range(rows):
        writer.writerow([
            f"{i}",                                 # id
            f"name_{i}",                            # name
            f"{i * 10}",                            # value
            f"2025-04-26T{i % 24:02d}:00:00Z",      # timestamp
            f"category_{i % 5}",                    # category
            f"subcategory_{i % 10}",                # subcategory
            "active" if i % 3 == 0 else "inactive", # status
            f"P{i % 3 + 1}",                        # priority
            f"{i * 5.25}",                          # amount
            f"This is a description for item {i}"   # description
        ])
    
    buffer.seek(0)
    return buffer.getvalue()


def setup_mock_s3_data():
    """Set up mock S3 buckets and test data."""
    # Create S3 client
    s3_client = boto3.client('s3', region_name='us-east-1')
    
    # Create test buckets
    s3_client.create_bucket(Bucket=TEST_INPUT_BUCKET)
    s3_client.create_bucket(Bucket=TEST_OUTPUT_BUCKET)
    
    # Generate and upload test files
    start_time = time.time()
    logger.info(f"Generating and uploading {NUM_TEST_FILES} test CSV files...")
    
    for i in range(NUM_TEST_FILES):
        # Generate test data
        csv_data = generate_test_csv_data()
        
        # Upload to S3
        key = f"{TEST_PREFIX}file_{i}.csv"
        s3_client.put_object(
            Bucket=TEST_INPUT_BUCKET,
            Key=key,
            Body=csv_data
        )
        
        logger.info(f"Uploaded test file {i+1}/{NUM_TEST_FILES}: {key}")
    
    elapsed = time.time() - start_time
    logger.info(f"Setup completed in {elapsed:.2f} seconds")


def list_mock_s3_files(bucket, prefix=""):
    """List files in the mock S3 bucket."""
    s3_client = boto3.client('s3', region_name='us-east-1')
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    if "Contents" in response:
        for obj in response["Contents"]:
            logger.info(f"S3://{bucket}/{obj['Key']} - {obj['Size']} bytes")
    else:
        logger.info(f"No objects found in s3://{bucket}/{prefix}")


def save_mock_s3_file_locally(bucket, key, local_path):
    """Download a file from mock S3 to the local filesystem."""
    s3_client = boto3.client('s3', region_name='us-east-1')
    s3_client.download_file(bucket, key, local_path)
    logger.info(f"Downloaded s3://{bucket}/{key} to {local_path}")


def create_local_output_directory():
    """Create a local directory for saving output files."""
    output_dir = Path("local_test_output")
    output_dir.mkdir(exist_ok=True)
    return output_dir


@mock_aws
def run_local_test(with_wrangler=False, download_samples=True):
    """Run a local test of the S3 data processor using moto."""
    logger.info("Starting local test of S3 Data Processor")
    logger.info(f"Using AWS Data Wrangler: {with_wrangler}")
    
    # Set up mock S3 buckets and test data
    setup_mock_s3_data()
    
    # List input files
    logger.info("Input files in S3:")
    list_mock_s3_files(TEST_INPUT_BUCKET, TEST_PREFIX)
    
    # Create a processor instance
    # Note: AWS Data Wrangler won't work with moto, so we'll force it off
    processor = S3DataProcessor(
        input_bucket=TEST_INPUT_BUCKET,
        output_bucket=TEST_OUTPUT_BUCKET,
        prefix=TEST_PREFIX,
        max_workers=5,  # Using fewer workers for local testing
        use_wrangler=False,  # Force to False since Wrangler won't work with moto
        cache_size=32  # Smaller cache for testing
    )
    
    # Run the processor
    logger.info("Starting processing...")
    start_time = time.time()
    results = processor.process_all_files()
    elapsed = time.time() - start_time
    
    # Print results
    logger.info(f"Processing completed in {elapsed:.2f} seconds")
    logger.info(f"Files processed: {len(results)}")
    
    if results:
        times = list(results.values())
        logger.info(f"Average processing time per file: {sum(times)/len(times):.4f} seconds")
        logger.info(f"Fastest file: {min(times):.4f} seconds")
        logger.info(f"Slowest file: {max(times):.4f} seconds")
    
    # List output files
    logger.info("Output files in S3:")
    list_mock_s3_files(TEST_OUTPUT_BUCKET, "processed/")
    
    # Download sample output files if requested
    if download_samples and results:
        output_dir = create_local_output_directory()
        s3_client = boto3.client('s3', region_name='us-east-1')
        
        # Find sample output files
        response = s3_client.list_objects_v2(Bucket=TEST_OUTPUT_BUCKET, Prefix="processed/")
        if "Contents" in response and response["Contents"]:
            # Download a Parquet and Avro sample
            parquet_sample = next((obj["Key"] for obj in response["Contents"] if obj["Key"].endswith(".parquet")), None)
            avro_sample = next((obj["Key"] for obj in response["Contents"] if obj["Key"].endswith(".avro")), None)
            
            if parquet_sample:
                parquet_path = output_dir / Path(parquet_sample).name
                save_mock_s3_file_locally(TEST_OUTPUT_BUCKET, parquet_sample, str(parquet_path))
                
            if avro_sample:
                avro_path = output_dir / Path(avro_sample).name
                save_mock_s3_file_locally(TEST_OUTPUT_BUCKET, avro_sample, str(avro_path))
            
            logger.info(f"Sample files downloaded to {output_dir}")
    
    return results


def main():
    """Main entry point for the local test script."""
    # Run the test
    try:
        run_local_test(with_wrangler=False, download_samples=True)
        logger.info("Local test completed successfully")
    except Exception as e:
        logger.error(f"Error in local test: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()