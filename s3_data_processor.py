import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import io
import time
import concurrent.futures
import logging
from datetime import datetime
import awswrangler as wr
from functools import lru_cache
import os
from typing import List, Dict, Any, Tuple, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class S3DataProcessor:
    def __init__(self, input_bucket: str, output_bucket: str = None, prefix: str = None, 
                 max_workers: int = 10, use_wrangler: bool = True, cache_size: int = 128):
        """
        Initialize the S3 data processor.
        
        Args:
            input_bucket: S3 bucket containing input files
            output_bucket: S3 bucket for processed outputs (defaults to input_bucket if None)
            prefix: S3 prefix for input files
            max_workers: Maximum number of concurrent workers
            use_wrangler: Whether to use AWS Data Wrangler for optimized I/O
            cache_size: Size of LRU cache for file data
        """
        self.s3_client = boto3.client('s3')
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket or input_bucket
        self.prefix = prefix
        self.max_workers = max_workers
        self.use_wrangler = use_wrangler
        self.cache_size = cache_size
        
        # Create session with increased max_pool_connections
        self.session = boto3.Session()
        if not self.use_wrangler:
            self.s3_resource = self.session.resource('s3', 
                config=boto3.config.Config(max_pool_connections=50))
    
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
    
    def write_parquet_to_s3(self, df: pd.DataFrame, bucket: str, key: str) -> None:
        """Write a DataFrame to S3 as Parquet."""
        start_time = time.time()
        
        if self.use_wrangler:
            # Use AWS Data Wrangler for optimized S3 Parquet writing
            wr.s3.to_parquet(
                df=df,
                path=f"s3://{bucket}/{key}",
                compression="snappy",
                dataset=False
            )
        else:
            # Manual write using PyArrow
            buffer = io.BytesIO()
            table = pa.Table.from_pandas(df)
            pq.write_table(table, buffer, compression="snappy")
            buffer.seek(0)
            
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=buffer.getvalue()
            )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Parquet file written to s3://{bucket}/{key} in {elapsed:.6f}s")
    
    def write_avro_to_s3(self, df: pd.DataFrame, bucket: str, key: str) -> None:
        """Write a DataFrame to S3 as Avro."""
        start_time = time.time()
        
        if self.use_wrangler:
            # Use AWS Data Wrangler for Avro conversion
            wr.s3.to_avro(
                df=df,
                path=f"s3://{bucket}/{key}"
            )
        else:
            # For Avro without wrangler, one would typically use fastavro
            # This is a simplified implementation
            import fastavro
            schema = {
                "type": "record",
                "name": "data",
                "fields": [{"name": col, "type": ["null", "string"]} for col in df.columns]
            }
            
            records = df.to_dict("records")
            buffer = io.BytesIO()
            fastavro.writer(buffer, schema, records)
            buffer.seek(0)
            
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=buffer.getvalue()
            )
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Avro file written to s3://{bucket}/{key} in {elapsed:.6f}s")
    
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
    """Main function to run the S3 data processor."""
    # These should be environment variables in production
    INPUT_BUCKET = "mesenet-inputs"
    OUTPUT_BUCKET = "mesenet-harmonized-data"
    PREFIX = "iowa/20250318/"
    
    # Configuration parameters
    USE_WRANGLER = True
    MAX_WORKERS = 20
    CACHE_SIZE = 128
    
    processor = S3DataProcessor(
        input_bucket=INPUT_BUCKET,
        output_bucket=OUTPUT_BUCKET,
        prefix=PREFIX,
        max_workers=MAX_WORKERS,
        use_wrangler=USE_WRANGLER,
        cache_size=CACHE_SIZE
    )
    
    logger.info("Starting S3 data processing job")
    results = processor.process_all_files()
    
    # Print performance statistics
    if results:
        times = list(results.values())
        logger.info(f"Performance statistics:")
        logger.info(f"  - Total files processed: {len(times)}")
        logger.info(f"  - Average processing time: {sum(times)/len(times):.4f} seconds")
        logger.info(f"  - Fastest file: {min(times):.4f} seconds")
        logger.info(f"  - Slowest file: {max(times):.4f} seconds")
    
    logger.info("Processing complete!")


if __name__ == "__main__":
    main() 