import json
import os
import boto3

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
# Name of the table that stores the price
TABLE_NAME = os.environ.get('PRICE_CONFIG_TABLE_NAME', 'EventPriceConfig')
price_table = dynamodb.Table(TABLE_NAME)

# The fixed ID for the single item in our table that holds the price
PRICE_CONFIG_ID = 'current_event_price'

def lambda_handler(event, context):
    """
    Handles POST requests to remove the fixed event price.
    This function must be protected by a Cognito Authorizer in API Gateway.
    """
    # Standard CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS' # Or DELETE, if you prefer
    }

    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    try:
        # --- Delete from DynamoDB ---
        # This action removes the item with the specified key.
        # If the item doesn't exist, it will not raise an error.
        price_table.delete_item(
            Key={
                'configId': PRICE_CONFIG_ID
            }
        )
        
        print(f"Successfully removed the fixed price configuration.")

        # --- Success Response ---
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'message': 'Fixed price successfully removed.'
            })
        }

    except Exception as e:
        # This will catch potential IAM permission errors or other AWS issues.
        print(f"Internal Server Error: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'message': 'An internal error occurred while removing the price.'})
        }
