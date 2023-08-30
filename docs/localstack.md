How to Use Localstack in Your Development Work
==================================



### Install Docker Desktop (One-Time)

* https://docs.docker.com/desktop/install/mac-install/


### Install Localstack (One-Time)

* >pip install --upgrade localstack
* >localstack --version  # should be 2.2.0 or later


### Add LOCALSTACK_ENDPOINT_URL to Your .env File (One-Time)

* Find the value in the sample.env file  (# LOCALSTACK_ENDPOINT_URL=http://localhost:4566).  
* Copy and uncomment it into your .env file

### Run with Localstack (Recurring)

#### Start Docker Desktop and localstack image

* Open Docker Desktop from Finder
* Images->Local->localstack/localstack click on the start button on the right hand side to get the localstack
  docker image going


#### Start Localstack

* From your project directory in a separate terminal window, either:
* >localstack start
* >pipenv run localstack start

#### Proceed With Your Usual Development Activities

Assuming you followed all these steps and nothing went wrong, you should be running with localstack for SNS now.
You should be able to send an SMS message in the UI and observe it in the dashboard moving from Pending to Delivered
over a period of five minutes.  And you should not receive a text message.

NOTE: You will still be prompted for a 2FA code when you log in, but you will not receive a text message on any device.
To login, enter any six digit number.