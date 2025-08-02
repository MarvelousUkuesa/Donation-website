
#!/bin/bash

# An array of your function names
functions=(
  "unset-price-event"
  "ProcessDonation"
  "set_event_price"
  "getDonationDetials"
  "get_event_price"
  "handle_stripe_webhook"
  "validate_ticket"
)

for func_name in "${functions[@]}"; do
  echo "--- Attempting to delete function: $func_name ---"
  # This command will delete the function. 
  # It will show an error if the function doesn't exist, which is safe to ignore.
  aws lambda delete-function --function-name "$func_name"
done

echo "Cleanup complete. All specified functions have been removed."