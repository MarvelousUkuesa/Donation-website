import json
import os
import boto3
from decimal import Decimal
from datetime import datetime, timedelta, timezone # Import for time calculations
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

dynamodb = boto3.resource('dynamodb')
DONATION_TABLE_NAME = os.environ.get('DONATION_TABLE_NAME', 'DonationRecords')
donation_table = dynamodb.Table(DONATION_TABLE_NAME)

def lambda_handler(event, context):
    print(f"Received validation request event: {json.dumps(event)}")

    # Define CORS headers for the response
    cors_headers = {
        'Access-Control-Allow-Origin': '*', # Restrict this in production to your admin tool's domain
        'Access-Control-Allow-Headers': 'Content-Type,Authorization', # Include Authorization for API Key/Authorizer
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }

    # Handle CORS preflight request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }

    try:
        # Expecting verificationId in the request body for POST method
        body = json.loads(event.get('body', '{}'))
        verification_id = body.get('verificationId')

        if not verification_id:
            return create_response(400, {'message': 'Verification ID is required.', 'valid': False, 'reason': 'Missing ID'}, cors_headers)

        # Query DynamoDB using the verificationId (GSI)
        response = donation_table.query(
            IndexName='verificationId-index', # IMPORTANT: Ensure this GSI exists
            KeyConditionExpression=boto3.dynamodb.conditions.Key('verificationId').eq(verification_id)
        )

        items = response.get('Items', [])
        
        if not items:
            print(f"No donation record found for verification ID: {verification_id}")
            return create_response(404, {'message': 'Ticket not found.', 'valid': False, 'reason': 'Ticket not found'}, cors_headers)

        # Assume verificationId is unique, take the first item
        item = items[0] 
        donation_id = item['donationId']
        
        # Retrieve all necessary fields for validation
        status = item.get('status')
        is_redeemed_db = item.get('redeemed', False) # Use 'redeemed' attribute
        redeemed_time_db = item.get('redeemedTime') # Initialize here, might be None
        expiration_time_utc_db = item.get('expirationTime', 0) # 8 AM next day expiration
        creation_time_utc_db = item.get('creationTime', 0) # Purchase time

        current_time_utc = int(datetime.now(timezone.utc).timestamp())
        
        # Calculate the end of the 2-hour window from the creation time
        # FIX: Cast Decimal from DynamoDB to int for calculation
        two_hour_window_end_time = int(creation_time_utc_db) + (2 * 60 * 60) # 2 hours in seconds

        is_valid = True
        reason = "Ticket is valid."
        action_taken = "none" # To indicate if redemption happened in this call

        # --- Validation Rules ---
        # 1. Check if status is 'completed'
        if status != 'completed':
            is_valid = False
            reason = "Ticket status is not 'completed'. Payment might be pending or failed."
            print(f"Ticket {verification_id} invalid: status is {status}")

        # 2. Check if already redeemed
        elif is_redeemed_db: # Use the value from DB
            is_valid = False
            redeemed_timestamp = item.get('redeemedTime')
            # FIX: Cast the Decimal timestamp from DynamoDB to an integer before using it
            redeemed_dt = datetime.fromtimestamp(int(redeemed_timestamp), tz=timezone.utc) if redeemed_timestamp else None
            reason = f"Ticket has already been redeemed at {redeemed_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}." if redeemed_dt else "Ticket has already been redeemed."
            print(f"Ticket {verification_id} invalid: already redeemed.")

        # 3. Check general expiration time (8 AM next day UTC)
        # FIX: Cast Decimal from DynamoDB to int for comparison
        elif current_time_utc > int(expiration_time_utc_db):
            is_valid = False
            reason = "Ticket has expired (past 5 AM UTC next day)." # Note: Your SES email says 5 AM, Lambda calculates 5 AM, so updated message.
            print(f"Ticket {verification_id} invalid: expired at {expiration_time_utc_db}")
        
        # 4. Check the 2-hour window
        elif current_time_utc > two_hour_window_end_time:
            is_valid = False
            reason = "Ticket is no longer valid (exceeded 2-hour validation window from purchase)."
            print(f"Ticket {verification_id} invalid: exceeded 2-hour window. Current: {current_time_utc}, 2hr-end: {two_hour_window_end_time}")

        # --- Redemption Logic (if valid) ---
        if is_valid:
            try:
                redeem_timestamp = int(datetime.now(timezone.utc).timestamp())
                # Use ConditionExpression to ensure we only redeem if not already redeemed (to prevent race conditions)
                donation_table.update_item(
                    Key={'donationId': donation_id},
                    UpdateExpression="SET redeemed = :r, redeemedTime = :rt",
                    ConditionExpression="attribute_not_exists(redeemed) OR redeemed = :false_val", # Only update if 'redeemed' doesn't exist or is False
                    ExpressionAttributeValues={
                        ':r': True,
                        ':rt': redeem_timestamp,
                        ':false_val': False # Value for the condition check
                    }
                )
                action_taken = "redeemed"
                reason = "Ticket is valid and has been redeemed."
                print(f"Ticket {verification_id} successfully redeemed at {datetime.fromtimestamp(redeem_timestamp, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}.")
                
                # Update the redeemed status for the response
                is_redeemed_db = True
                redeemed_time_db = redeem_timestamp

            except ClientError as ce:
                if ce.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    # This means the ticket was already redeemed by another concurrent request
                    is_valid = False
                    reason = "Ticket has already been redeemed by another process."
                    action_taken = "failed_redeem_concurrent"
                    print(f"Ticket {verification_id} invalid: concurrent redemption attempt.")
                else:
                    raise # Re-raise other ClientErrors
            except Exception as update_error:
                print(f"Error redeeming ticket {verification_id} in DynamoDB: {update_error}")
                is_valid = False
                reason = "Internal error during ticket redemption."
                action_taken = "failed_redeem_general"


        # Prepare response data, including all relevant details for the frontend
        response_data = {
            'valid': is_valid,
            'reason': reason,
            'donationId': donation_id,
            'verificationId': verification_id,
            'status': status, # Original status from DB ('completed')
            'payerEmail': item.get('payerEmail'),
            'amount': item.get('amount'),
            'currency': item.get('currency'),
            'creationTime': creation_time_utc_db,
            'expirationTime': expiration_time_utc_db,
            'currentTime': current_time_utc,
            'redeemed': is_redeemed_db, # Current redeemed status (after potential update)
            'redeemedTime': redeemed_time_db, # Current redeemed time (after potential update)
            'actionTaken': action_taken # What action was taken by this Lambda call
        }

        return create_response(200, response_data, cors_headers)

    except Exception as e:
        print(f"Error during validation: {e}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'message': 'Internal server error.', 'valid': False, 'reason': 'Internal server error'}, cors_headers)

# --- Helper function to create a standardized Lambda proxy response ---
def create_response(status_code, body_content, headers):
    """Helper function to create a standardized Lambda proxy response."""
    if isinstance(body_content, str):
        # If a string is passed, wrap it in a dictionary with 'message' and a generic 'error' status
        body_dict = {'message': body_content}
    else:
        body_dict = body_content

    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(body_dict, cls=DecimalEncoder)
    }
