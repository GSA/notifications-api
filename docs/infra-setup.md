# Setting up the infrastructure

## Steps to prepare SES

1. Go to SES console for \$AWS_REGION and create new origin and destination emails. AWS will send a verification via email which you'll need to complete.
2. Find and replace instances in the repo of "testsender", "testreceiver" and "dispostable.com", with your origin and destination email addresses, which you verified in step 1 above.

TODO: create env vars for these origin and destination email addresses for the root service, and create new migrations to update postgres seed fixtures

## Steps to prepare SNS

1. Go to Pinpoints console for \$AWS_PINPOINT_REGION and choose "create new project", then "configure for sms"
2. Tick the box at the top to enable SMS, choose "transactional" as the default type and save
3. In the lefthand sidebar, go the "SMS and Voice" (bottom) and choose "Phone Numbers"
4. Under "Number Settings" choose "Request Phone Number"
5. Choose Toll-free number, tick SMS, untick Voice, choose "transactional", hit next and then "request"
6. Go to SNS console for \$AWS_PINPOINT_REGION, look at lefthand sidebar under "Mobile" and go to "Text Messaging (SMS)"
7. Scroll down to "Sandbox destination phone numbers" and tap "Add phone number" then follow the steps to verify (you'll need to be able to retrieve a code sent to each number)

At this point, you _should_ be able to complete both the email and phone verification steps of the Notify user sign up process! 🎉