#!/bin/bash

# Script to set up and run local tests for the S3 Data Processor

echo "Setting up environment for S3 Data Processor local testing"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Create simplified requirements file if it doesn't exist
if [ ! -f "requirements_local.txt" ]; then
    echo "Creating requirements_local.txt..."
    cat > requirements_local.txt << EOL
boto3>=1.26.0
pandas>=1.5.0
pyarrow>=8.0.0
moto>=4.1.0
pytest>=7.0.0
EOL
fi

# Install required packages
echo "Installing required packages..."
pip install -r requirements_local.txt

# Run the local test script
echo "Running local test..."
python local_test.py

# Check if output directory exists
if [ -d "local_test_output" ]; then
    echo "Test outputs available in the local_test_output directory"
    ls -la local_test_output
fi

echo "Local test completed"