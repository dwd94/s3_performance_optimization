import json
import os
import logging
import traceback
from s3_data_processor import S3DataProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    """
    AWS Lambda handler function for S3 data processing.
    
    This function can be triggered by:
    1. S3 event notifications
    2. EventBridge scheduled events
    3. Direct invocation
    
    Args:
        event: Lambda event data
        context: Lambda context object
    
    Returns:
        Dict containing execution results
    """
    try:
        logger.info(f"Lambda function ARN: {context.invoked_function_arn}")
        logger.info(f"Lambda function version: {context.function_version}")
        logger.info(f"Lambda request ID: {context.aws_request_id}")
        
        # Get environment variables with defaults
        input_bucket = os.environ.get('INPUT_BUCKET')
        output_bucket = os.environ.get('OUTPUT_BUCKET')
        prefix = os.environ.get('PREFIX', '')
        max_workers = int(os.environ.get('MAX_WORKERS', '20'))
        use_wrangler = os.environ.get('USE_WRANGLER', 'True').lower() == 'true'
        cache_size = int(os.environ.get('CACHE_SIZE', '128'))
        
        # Check for required environment variables
        if not input_bucket:
            raise ValueError("INPUT_BUCKET environment variable is required")
        
        # Initialize processor
        processor = S3DataProcessor(
            input_bucket=input_bucket,
            output_bucket=output_bucket,
            prefix=prefix,
            max_workers=max_workers,
            use_wrangler=use_wrangler,
            cache_size=cache_size
        )
        
        # Check if this is an S3 event
        if 'Records' in event and len(event['Records']) > 0 and 's3' in event['Records'][0]:
            # Process specific S3 objects from event
            results = process_s3_event(event, processor)
        else:
            # Process all files in the bucket with the specified prefix
            results = processor.process_all_files()
        
        # Calculate statistics
        stats = calculate_statistics(results)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Processing completed successfully',
                'files_processed': len(results),
                'statistics': stats
            })
        }
    
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        logger.error(traceback.format_exc())
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': f'Error processing files: {str(e)}',
                'error_type': type(e).__name__
            })
        }

def process_s3_event(event, processor):
    """
    Process objects from an S3 event notification.
    
    Args:
        event: S3 event notification
        processor: S3DataProcessor instance
    
    Returns:
        Dict of processing results
    """
    results = {}
    
    for record in event['Records']:
        if 's3' in record and 'object' in record['s3'] and 'bucket' in record['s3']:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            # Create an object dict similar to what list_objects_v2 returns
            obj = {
                'Key': key,
                'Size': record['s3']['object'].get('size', 0),
                'LastModified': record['eventTime']
            }
            
            logger.info(f"Processing S3 event for s3://{bucket}/{key}")
            file_key, elapsed = processor.process_file(obj)
            
            if elapsed > 0:
                results[file_key] = elapsed
    
    return results

def calculate_statistics(results):
    """
    Calculate processing statistics.
    
    Args:
        results: Dict of file keys and processing times
    
    Returns:
        Dict of statistics
    """
    if not results:
        return {
            'total_files': 0,
            'total_time': 0,
            'average_time': 0,
            'min_time': 0,
            'max_time': 0
        }
    
    times = list(results.values())
    
    return {
        'total_files': len(times),
        'total_time': sum(times),
        'average_time': sum(times) / len(times),
        'min_time': min(times),
        'max_time': max(times)
    }

if __name__ == "__main__":
    # For local testing
    test_event = {
        'Records': []  # Empty event to process all files
    }
    
    class MockContext:
        def __init__(self):
            self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
            self.function_version = "$LATEST"
            self.aws_request_id = "00000000-0000-0000-0000-000000000000"
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2)) 