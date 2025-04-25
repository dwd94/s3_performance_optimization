"""
Simplified S3 Data Processor for local testing.
This version removes the AWS Data Wrangler dependency for easier local testing.
"""

import boto3
import pandas as pd
import io
import time
import concurrent.futures
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import List, Dict, Any, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class S3DataProcessor:
    def __init__(self, input_bucket: str, output_bucket: str = None, prefix: str = None, 
                 max_workers: int = 10, use_wrangler: bool = False, cache_size: int = 128):
        """
        Initialize the S3 data processor.
        
        Args:
            input_bucket: S3 bucket containing input files
            output_bucket: S3 bucket for processed outputs (defaults to input_bucket if None)
            prefix: S3 prefix for input files
            max_workers: Maximum number of concurrent workers
            use_wrangler: Whether to use AWS Data Wrangler (not used in simplified version)
            cache_size: Size of LRU cache for file data
        """
        self.s3_client = boto3.client('s3')
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket or input_bucket
        self.prefix = prefix
        self.max_workers = max_workers
        self.use_wrangler = False  # Force to False in simplified version
        self.cache_size = cache_size
        
        # Create session with increased max_pool_connections
        self.session = boto3.Session()
        # Simplified for local testing
        self.s3_resource = self.session.resource('s3')
    
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
    
    def read_csv_to_dataframe(self, bucket: str, key: str) -> pd.DataFrame:
        """Read a CSV file from S3 into a pandas DataFrame."""
        start_time = time.time()
        
        # Standard pandas read (no AWS Data Wrangler in simplified version)
        data = self.read_s3_file(bucket, key)
        df = pd.read_csv(io.BytesIO(data))
        
        elapsed = time.time() - start_time
        logger.info(f"✅ CSV file read from s3://{bucket}/{key} in {elapsed:.6f}s")
        return df
    
    def write_parquet_to_s3(self, df: pd.DataFrame, bucket: str, key: str) -> None:
        """Write a DataFrame to S3 as Parquet."""
        start_time = time.time()
        
        # Use pandas to_parquet for simplicity in this simplified version
        buffer = io.BytesIO()
        df.to_parquet(buffer, compression="snappy")
        buffer.seek(0)
        
        self.s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue()
        )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Parquet file written to s3://{bucket}/{key} in {elapsed:.6f}s")
    
    def write_avro_to_s3(self, df: pd.DataFrame, bucket: str, key: str) -> None:
        """
        Write a DataFrame to S3 as Avro.
        This is a simplified version that just writes a CSV for testing.
        In a real implementation, you would use fastavro or another Avro library.
        """
        start_time = time.time()
        
        # For simplicity in the simplified version, we'll just write a CSV instead of Avro
        buffer = io.BytesIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        
        self.s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue()
        )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ CSV file (mock Avro) written to s3://{bucket}/{key} in {elapsed:.6f}s")
    
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


def main():
    """Main function to run the S3 data processor (for direct script execution)."""
    logger.info("This is a simplified version for local testing.")
    logger.info("Use local_test.py to run tests with mock S3.")


if __name__ == "__main__":
    main() 