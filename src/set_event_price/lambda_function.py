import json
import os
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('PRICE_CONFIG_TABLE_NAME', 'EventPriceConfig')
price_table = dynamodb.Table(TABLE_NAME)
PRICE_CONFIG_ID = 'current_event_price'

def lambda_handler(event, context):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    try:
        body = json.loads(event.get('body', '{}'))
        price_raw = body.get('price')
        event_name = body.get('eventName') # NEW: Get event name

        # --- Validation ---
        if not event_name or not isinstance(event_name, str):
            raise ValueError("Event name is missing or invalid.")
        
        if price_raw is None:
            raise ValueError("Price is missing from the request body.")

        try:
            price_in_cents = int(price_raw)
        except (ValueError, TypeError):
            raise ValueError("Price must be a valid number.")

        if price_in_cents <= 0:
            raise ValueError("Price must be a positive number.")

        # --- Save to DynamoDB ---
        price_table.put_item(
            Item={
                'configId': PRICE_CONFIG_ID,
                'priceInCents': Decimal(price_in_cents),
                'eventName': event_name, # NEW: Save event name
                'lastUpdated': Decimal(int(context.get_remaining_time_in_millis()))
            }
        )
        
        print(f"Successfully set event '{event_name}' to {price_in_cents} cents.")

        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'message': 'Price set successfully',
                'price': price_in_cents,
                'eventName': event_name
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'message': f'An internal error occurred: {str(e)}'})
        }
