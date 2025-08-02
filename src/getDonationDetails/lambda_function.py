import json
import os
import boto3
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to handle Decimal types, converting them to int or float.
    This is necessary because DynamoDB returns numbers as Decimal objects,
    which are not directly serializable to JSON.
    """
    def default(self, o):
        if isinstance(o, Decimal):
            # Check if the Decimal is an integer (no fractional part)
            if o % 1 == 0:
                return int(o)
            else:
                return float(o)
        return super(DecimalEncoder, self).default(o)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
# Get the DynamoDB table name from environment variables, with a fallback
DONATION_TABLE_NAME = os.environ.get('DONATION_TABLE_NAME', 'DonationRecords')
donation_table = dynamodb.Table(DONATION_TABLE_NAME)

def lambda_handler(event, context):
    """
    AWS Lambda function to retrieve donation details based on a session ID.
    It queries a DynamoDB table using a Global Secondary Index (GSI) on checkoutSessionId.
    Handles CORS preflight requests and returns donation details or appropriate error/status codes.
    """
    # Define CORS headers that will be used in every response
    cors_headers = {
        'Access-Control-Allow-Origin': '*', # IMPORTANT: For production, restrict this to your actual frontend domain
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, OPTIONS' # This Lambda is designed for GET requests
    }

    # Handle CORS preflight request (OPTIONS method)
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': '' # No body needed for preflight response
        }

    try:
        # Extract sessionId from query parameters for GET requests
        session_id = event.get('queryStringParameters', {}).get('sessionId')

        # Validate if sessionId is provided
        if not session_id:
            return {
                'statusCode': 400, # Bad Request
                'headers': cors_headers,
                'body': json.dumps({'error': 'sessionId is required'})
            }

        # Query DynamoDB using the 'checkoutSessionId-index' GSI
        # This index should be created on your DynamoDB table with checkoutSessionId as the partition key.
        response = donation_table.query(
            IndexName='checkoutSessionId-index',
            KeyConditionExpression=boto3.dynamodb.conditions.Key('checkoutSessionId').eq(session_id)
        )

        # Check if any item was found
        # Corrected indentation here and for all subsequent blocks within this 'if'
        if response['Items']:
            item = response['Items'][0] # Get the first item found (assuming sessionId is unique)
            status = item.get('status') # Get the status of the donation record

            # Prepare common response data structure
            base_response_data = {
                'verificationId': item.get('verificationId'),
                'amount': item.get('amount'),
                'currency': item.get('currency'),
                'payerEmail': item.get('payerEmail'),
                'creationTime': item.get('creationTime'),
                'expirationTime': item.get('expirationTime'),
                'redeemed': item.get('redeemed', False),
                'redeemedTime': item.get('redeemedTime', None),
                'donationId': item.get('donationId')
            }

            # Logic based on the donation status
            if status == 'completed':
                # If status is 'completed', return as 'succeeded' to the frontend
                base_response_data['status'] = 'succeeded'
                return {
                    'statusCode': 200, # OK
                    'headers': cors_headers,
                    'body': json.dumps(base_response_data, cls=DecimalEncoder)
                }
            elif status == 'pending':
                # For testing: if status is 'pending', simulate a 'succeeded' response
                # This allows the frontend to display the success page for pending donations during testing.
                base_response_data['status'] = 'succeeded' # Frontend will see 'succeeded'
                return {
                    'statusCode': 200, # OK
                    'headers': cors_headers,
                    'body': json.dumps(base_response_data, cls=DecimalEncoder)
                }
            else:
                # Handle other unexpected statuses (e.g., 'failed', 'canceled')
                return {
                    'statusCode': 409, # Conflict (or another appropriate client error code)
                    'headers': cors_headers,
                    'body': json.dumps({'error': f'Donation has an unexpected status: {status}', 'status': status})
                }
        else:
            # If no item is found for the given sessionId, return 404
            # This might happen if the webhook hasn't processed the payment yet.
            return {
                'statusCode': 404, # Not Found
                'headers': cors_headers,
                'body': json.dumps({'error': 'Donation record not yet found. Retrying...', 'status': 'not_found'})
            }

    except Exception as e:
        # Catch any unexpected errors and return a 500 Internal Server Error
        print(f"Error: {e}")
        import traceback
        traceback.print_exc() # Print full traceback to CloudWatch logs for debugging
        return {
            'statusCode': 500, # Internal Server Error
            'headers': cors_headers,
            'body': json.dumps({'error': 'Internal server error'})
        }
