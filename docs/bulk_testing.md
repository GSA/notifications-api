How to Run a Bulk Send Simulation
==================================

Assuming that you have followed all steps to set up localstack successfully, do the following:

1. Create an sms template that requires no inputs from the user (i.e. the csv file will only have phone numbers)
2. Uncomment the test 'test_generate_csv_for_bulk_testing' in app/test_utils.py
3. Run `make test` on this project.  This will generate the csv file for the bulk test.
4. If you are not a platform admin for your service when you run locally, do the following:
   - >psql -d notification_api
   - update users set platform_admin='t';
   - \q
   - sign out
   - sign in.
   - Go to settings and set the organization for your service to 'Broadcast services' (scroll down to platform admin)
   - Go to settings and set your service to 'live' (scroll down to platform admin)
5. Run your app 'locally'.  I.e. run `make run-procfile` on this project and `make run-flask` on the admin project
6. Sign in.  Verify you are running with localstack.  I.e., you do NOT receive a text message on sign in.  Instead, 
   you see your authentication code in green in the api logs
7. Go to send messages and upload your csv file and send your 100000 messages