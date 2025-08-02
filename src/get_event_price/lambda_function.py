import json
import os
import boto3
from decimal import Decimal

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            if o % 1 == 0:
                return int(o)
            else:
                return float(o)
        return super(DecimalEncoder, self).default(o)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('PRICE_CONFIG_TABLE_NAME', 'EventPriceConfig')
price_table = dynamodb.Table(TABLE_NAME)
PRICE_CONFIG_ID = 'current_event_price'

def lambda_handler(event, context):
    """
    Handles GET requests to fetch the current fixed event price.
    This function should be publicly accessible.
    """
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    try:
        # --- Fetch from DynamoDB ---
        response = price_table.get_item(
            Key={'configId': PRICE_CONFIG_ID}
        )
        
        item = response.get('Item')

        if not item:
            # If no item is found, it means no price has been set yet.
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'message': 'No fixed price has been set.'})
            }

        # --- Success Response ---
        return {
            'statusCode': 200,
            'headers': headers,
            # Use the custom encoder to handle the Decimal type from DynamoDB
            'body': json.dumps(item, cls=DecimalEncoder)
        }
        
    except Exception as e:
        print(f"Internal Server Error: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'message': 'An internal error occurred.'})
        }
