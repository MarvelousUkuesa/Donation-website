import json
import os
import stripe
import boto3
import random
import string
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal
from botocore.exceptions import ClientError # For conditional update errors

class DecimalEncoder(json.JSONEncoder):
    """Helper to serialize Decimal types from DynamoDB to JSON."""
    def default(self, o):
        if isinstance(o, Decimal):
            if o % 1 == 0:
                return int(o)
            else:
                return float(o)
        return super(DecimalEncoder, self).default(o)

# --- AWS Service Clients ---
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses', region_name='eu-central-1')

# --- Environment Variables ---
DONATION_TABLE_NAME = os.environ.get('DONATION_TABLE_NAME', 'DonationRecords')
FROM_EMAIL_ADDRESS = os.environ.get('FROM_EMAIL_ADDRESS')
FALLBACK_FRONTEND_DOMAIN = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:3000')

donation_table = dynamodb.Table(DONATION_TABLE_NAME)

def generate_short_id(length=7):
    """Generates a short, human-readable, unique ID."""
    characters = string.ascii_uppercase + '23456789'
    short_id = ''.join(random.choices(characters, k=length))
    return short_id

def lambda_handler(event, context):
    """
    AWS Lambda function to handle Stripe webhook events.
    Processes 'checkout.session.completed' to update DynamoDB and send a verification email.
    """
    print("Stripe Webhook received!")
    
    payload = event.get('body')
    sig_header = event.get('headers', {}).get('Stripe-Signature')

    try:
        stripe_event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"Error verifying webhook signature: {e}")
        return {'statusCode': 400}

    if stripe_event['type'] == 'checkout.session.completed':
        session = stripe_event['data']['object']
        checkout_session_id = session.get('id')
        customer_email = session.get('customer_details', {}).get('email')
        amount_total = session.get('amount_total', 0) / 100

        print(f"Checkout Session Completed: {checkout_session_id}")

        try:
            # --- THIS IS THE FIX: Generate a short, human-readable verification ID ---
            verification_id = generate_short_id()
            
            now_utc = datetime.now(timezone.utc)
            creation_timestamp = int(now_utc.timestamp())
            
            tomorrow_utc = now_utc + timedelta(days=1)
            expiration_datetime = datetime.combine(tomorrow_utc.date(), time(5, 0), tzinfo=timezone.utc)
            expiration_timestamp = int(expiration_datetime.timestamp())

            response = donation_table.query(
                IndexName='checkoutSessionId-index',
                KeyConditionExpression=boto3.dynamodb.conditions.Key('checkoutSessionId').eq(checkout_session_id)
            )
            
            if not response['Items']:
                print(f"Error: No matching donation record found for session ID: {checkout_session_id}.")
                return {'statusCode': 200, 'body': json.dumps({'status': 'error', 'message': 'Donation record not found'})}

            donation_item = response['Items'][0]
            donation_id = donation_item['donationId']
            dynamic_frontend_domain = donation_item.get('frontendDomain', FALLBACK_FRONTEND_DOMAIN)

            donation_table.update_item(
                Key={'donationId': donation_id},
                UpdateExpression="SET #status = :s, #verificationId = :v, #expirationTime = :e, #redeemed = :r, #creationTime = :c, #payerEmail = :pe, #payerName = :pn",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#verificationId': 'verificationId',
                    '#expirationTime': 'expirationTime',
                    '#redeemed': 'redeemed',
                    '#creationTime': 'creationTime',
                    '#payerEmail': 'payerEmail',
                    '#payerName': 'payerName'
                },
                ExpressionAttributeValues={
                    ':s': 'completed',
                    ':v': verification_id,
                    ':e': expiration_timestamp,
                    ':r': False,
                    ':c': creation_timestamp,
                    ':pe': customer_email,
                    ':pn': session.get('customer_details', {}).get('name', 'N/A')
                }
            )
            print(f"Successfully updated donation {donation_id} with short verification ID: {verification_id}.")

            send_verification_email(customer_email, verification_id, amount_total, dynamic_frontend_domain)

        except Exception as e:
            print(f"Error during database update or email sending: {e}")
            import traceback
            traceback.print_exc()
            return {'statusCode': 200, 'body': json.dumps({'status': 'error', 'message': 'Internal server error'})}

    return {'statusCode': 200, 'body': json.dumps({'status': 'success'})}


def send_verification_email(to_email, verification_id, amount, frontend_domain):
    """
    Sends a verification email with a QR code and ticket details.
    """
    verification_url = f"{frontend_domain}/verify?id={verification_id}"
    qr_code_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={verification_url}"

    email_subject = "Your Donation Confirmation & Ticket"
    email_body_html = f"""
        <html>
        <head></head>
        <body style="font-family: Arial, sans-serif; text-align: center; color: #333;">
            <h2>Thank You for Your Donation!</h2>
            <p>We sincerely appreciate your generous donation of €{amount:.2f}.</p>
            <p>This QR code is your verifiable ticket. It is valid until 5:00 AM tomorrow (UTC).</p>
            <img src="{qr_code_url}" alt="Your Verification QR Code" style="max-width: 250px; height: auto; margin: 20px auto; display: block;">
            <p>Verification ID: <strong>{verification_id}</strong></p>
            <p>You can also verify your ticket directly by visiting: <a href="{verification_url}">{verification_url}</a></p>
            <p style="font-size: 0.8em; color: #666;">Please keep this email safe. For any questions, contact support.</p>
        </body>
        </html>
    """

    try:
        response = ses_client.send_email(
            Source=FROM_EMAIL_ADDRESS,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': email_subject},
                'Body': {'Html': {'Data': email_body_html}}
            }
        )
        print(f"Email sent successfully to {to_email}! Message ID: {response['MessageId']}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
