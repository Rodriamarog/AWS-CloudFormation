import json
import boto3
import hashlib
import os
from botocore.exceptions import ClientError

# Initialize AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

# DynamoDB table and SNS topic configuration
TABLE_NAME = os.environ.get('TABLE_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')

if not TABLE_NAME or not SNS_TOPIC_ARN:
    raise ValueError("Missing environment variable(s). TABLE_NAME and SNS_TOPIC_ARN must be set.")

def lambda_handler(event, context):
    # Extract bucket name and object key from the S3 event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    object_key = event['Records'][0]['s3']['object']['key']
    if "AWS_SAM_LOCAL" in os.environ:
        print("Running locally, using mocked file content.")
        file_content = b"Hello, this is a test content for hashing!"
    else:
        try:
            # Get the object from S3
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            file_content = response['Body'].read()

            # Calculate the file's SHA-256 hash
            file_hash = hashlib.sha256(file_content).hexdigest()

            # Check for the hash in the DynamoDB table
            table = dynamodb.Table(TABLE_NAME)
            db_response = table.get_item(Key={'HashKey': file_hash})

            if 'Item' in db_response:
                # Duplicate found, publish notification to SNS
                message = f"Duplicate file detected: {object_key} with hash {file_hash}"
                sns.publish(TopicArn=SNS_TOPIC_ARN, Message=message)
                return {"statusCode": 200, "body": json.dumps({"message": "Duplicate file detected and reported."})}
            else:
                # No duplicate, add hash to DynamoDB
                table.put_item(Item={'HashKey': file_hash, 'FileName': object_key})
                return {"statusCode": 200, "body": json.dumps({"message": "New file processed."})}

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            if error_code == 'NoSuchBucket':
                return {"statusCode": 404, "body": json.dumps({"message": f"Bucket '{bucket_name}' does not exist."})}
            elif error_code == 'NoSuchKey':
                return {"statusCode": 404, "body": json.dumps({"message": f"Object '{object_key}' does not exist in bucket '{bucket_name}'."})}
            elif error_code == 'AccessDenied':
                return {"statusCode": 403, "body": json.dumps({"message": "Access denied. Check your permissions."})}
            else:
                return {"statusCode": 500, "body": json.dumps({"message": f"Error processing the file: {error_message}"})}

        except Exception as e:
            return {"statusCode": 500, "body": json.dumps({"message": f"Unexpected error: {str(e)}"})}