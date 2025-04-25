# Local Testing Guide for S3 Data Processor

This guide provides instructions for testing the S3 Data Processor solution locally without requiring actual AWS resources.

## Overview

We've created a simplified testing environment that uses:

1. **Moto** - A popular library that mocks AWS services
2. **Simplified processor** - A version of our processor that doesn't rely on AWS Data Wrangler
3. **Local test script** - Generates test data and runs the processing workflow

## Prerequisites

- Python 3.7 or higher
- pip (Python package manager)
- Virtual environment (recommended)

## Setup and Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-directory>
```

### 2. Set Up a Virtual Environment (Recommended)

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements_local.txt
```

## Running the Tests

### Option 1: Using the Shell Script (Linux/macOS)

The simplest way to run the tests is to use the provided shell script:

```bash
# Make the script executable
chmod +x run_local_test.sh

# Run the script
./run_local_test.sh
```

### Option 2: Manual Execution

If you prefer to run the tests manually:

```bash
# Make sure your virtual environment is activated
python local_test.py
```

## Understanding the Test Environment

The local test environment consists of several components:

### 1. `s3_data_processor_simplified.py`

This is a simplified version of the main processor that:
- Removes AWS Data Wrangler dependency
- Uses pandas directly for Parquet conversion
- Substitutes CSV for Avro (since Avro requires additional dependencies)

### 2. `local_test.py`

This script:
- Sets up mock S3 buckets using Moto
- Generates test CSV data
- Runs the processor against the mock S3 environment
- Downloads sample output files locally

### 3. `requirements_local.txt`

Contains minimal dependencies needed for local testing.

## Test Output

After running the tests, you'll find:

1. **Console Output** showing:
   - Processing time for each file
   - Overall performance metrics
   - Any errors or warnings

2. **Local Files** in the `local_test_output` directory:
   - Sample Parquet file
   - Sample "Avro" file (actually CSV in the simplified version)

## Modifying the Tests

You can customize the tests by editing `local_test.py`:

- `NUM_TEST_FILES`: Change the number of test files (default: 10)
- `ROWS_PER_FILE`: Change the number of rows per test file (default: 1000)
- `CSV_COLUMNS`: Modify the test data structure

## Limitations

The local testing environment has some limitations:

1. No actual AWS Data Wrangler integration (it doesn't work with Moto)
2. Simplified Avro implementation (uses CSV instead)
3. Performance metrics won't match actual AWS environment

## Troubleshooting

### Common Issues

1. **Import errors**:
   - Make sure all dependencies are installed
   - Verify your virtual environment is activated

2. **Permission errors** (Linux/macOS):
   - Make sure the shell script is executable (`chmod +x run_local_test.sh`)

3. **Memory issues with large test files**:
   - Reduce `NUM_TEST_FILES` or `ROWS_PER_FILE` in `local_test.py` 