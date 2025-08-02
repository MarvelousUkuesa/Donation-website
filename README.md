Donation Website Backend
This project contains the complete serverless backend for a donation and ticketing website, built using the AWS Serverless Application Model (SAM). It provides a suite of Lambda functions to manage event pricing, process donations, validate tickets, and handle payments via Stripe.

The infrastructure, including the API Gateway, Lambda functions, IAM roles, and security, is defined in the template.yaml file.

Core Features
This backend consists of seven serverless functions:

set_event_price: (Private) Sets a fixed price for an event.

get_event_price: (Public) Retrieves the current price for an event.

unset-price-event: (Private) Removes the price for an event, making it donation-based.

ProcessDonation: (Public) Creates a payment intention to process a donation or ticket purchase.

handle_stripe_webhook: (Public) Receives webhooks from Stripe to confirm payment success and update records.

getDonationDetails: (Private) Retrieves the details for a specific donation or ticket purchase.

validate_ticket: (Private) Validates a ticket ID.

Architecture
This application uses the following AWS services:

AWS Lambda: Hosts the business logic for all seven functions.

Amazon API Gateway: Provides the public HTTP endpoints for all functions.

Amazon DynamoDB: Used for storing donation records and event price configurations (Note: Tables are not defined in this template and must exist separately).

Amazon Cognito: Manages user authentication and secures private API endpoints.

Prerequisites
To build, deploy, and test this application, you will need the following tools installed:

AWS SAM CLI - Install the SAM CLI

Python 3.13

Docker - Install Docker Community Edition

Deployment
The entire application is deployed as a single CloudFormation stack using the SAM CLI.

First-Time Deployment

Run the following commands in your shell to build and deploy the application for the first time:

# Build the source code and dependencies

sam build

# Deploy the application with a guided process

sam deploy --guided

The guided deployment will prompt you for several parameters:

Stack Name: A unique name for your stack, e.g., donation-website-backend.

AWS Region: The AWS region to deploy to (e.g., eu-central-1).

Parameter CognitoUserPoolArn: (Important) You must provide the full ARN of your existing Amazon Cognito User Pool.

Confirm changes before deploy: Y. This allows you to review changes before they are applied.

Allow SAM CLI IAM role creation: Y. This is required as the template creates IAM roles for the Lambda functions.

Save arguments to samconfig.toml: Y. This saves your choices so future deployments are faster.

Subsequent Deployments

After the first deployment, you can simply run the following commands to deploy any changes:

sam build
sam deploy

API Endpoints
After a successful deployment, you can find your API Gateway URL in the Outputs section of the CloudFormation stack.

The following endpoints will be available:

Method

Path

Authentication

Description

POST

/validate_ticket/set-price

Cognito

Sets the price for an event.

GET

/get-price

None

Gets the price for an event.

POST

/validate_ticket/unset-price

Cognito

Removes the price for an event.

POST

/ProcessDonation

None

Initiates a donation or ticket purchase.

POST

/handle_stripe_webhook

None

Handles payment confirmation from Stripe.

GET

/getDonationDetials/{donationId}

Cognito

Retrieves details of a specific donation.

POST

/validate_ticket

Cognito

Validates a ticket ID.

Local Testing
You can run the API locally to test your functions without deploying to AWS.

# Build the application

sam build

# Start the local API on http://localhost:3000

sam local start-api

You can then make requests to the local endpoints (e.g., curl http://localhost:3000/get-price).

Cleanup
To delete the application and all related resources from your AWS account, run the sam delete command:

sam delete
