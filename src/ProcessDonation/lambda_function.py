import json
import os
import stripe
import boto3
import uuid
import time
from decimal import Decimal

# --- Environment Variables ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
DONATION_TABLE_NAME = os.environ.get('DONATION_TABLE_NAME', 'DonationRecords')
PRICE_CONFIG_TABLE_NAME = os.environ.get('PRICE_CONFIG_TABLE_NAME', 'EventPriceConfig')
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:3000')

# --- AWS Service Clients ---
dynamodb = boto3.resource('dynamodb')
donation_table = dynamodb.Table(DONATION_TABLE_NAME)
price_table = dynamodb.Table(PRICE_CONFIG_TABLE_NAME)
PRICE_CONFIG_ID = 'current_event_price'

def lambda_handler(event, context):
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }
    if event.get('httpMethod') == 'OPTIONS':
        return { 'statusCode': 200, 'headers': cors_headers, 'body': '' }

    try:
        body = json.loads(event.get('body', '{}'))
        user_email = body.get('email')

        # --- Determine Amount: Check for a fixed price first ---
        try:
            price_config = price_table.get_item(Key={'configId': PRICE_CONFIG_ID}).get('Item')
        except Exception:
            price_config = None # If table/item doesn't exist, treat as no config

        if price_config:
            # A fixed price is set, use it
            donation_amount = int(price_config['priceInCents'])
            product_name = price_config.get('eventName', 'Event Ticket')
            product_description = 'Your entry ticket.'
        else:
            # No fixed price, use dynamic donation from request body
            donation_amount = body.get('amount')
            product_name = 'One-time Donation'
            product_description = 'Your generous contribution to our cause.'
        
        # --- Validation ---
        if not isinstance(donation_amount, int) or donation_amount < 100:
            raise ValueError("Invalid amount. Must be at least 1 EUR.")
        if not user_email:
            raise ValueError("Email is required.")

        # --- Create Stripe Checkout Session ---
        donation_id = str(uuid.uuid4())
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'unit_amount': donation_amount,
                    'product_data': { 'name': product_name, 'description': product_description },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'{FRONTEND_BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{FRONTEND_BASE_URL}?canceled=true',
            customer_email=user_email,
            metadata={'internal_donation_id': donation_id}
        )

        # --- Save initial record to DynamoDB ---
        item_to_save = {
            'donationId': donation_id,
            'checkoutSessionId': checkout_session.id,
            'amount': donation_amount,
            'currency': 'eur',
            'status': 'pending',
            'payerEmail': user_email,
            'timestamp': int(time.time())
        }
        if price_config: # If it was a fixed-price event, add the event name
            item_to_save['eventName'] = product_name
            
        donation_table.put_item(Item=item_to_save)

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'session_url': checkout_session.url})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'message': f'Internal server error: {str(e)}'})
        }
