How to Use Localstack in Your Development Work
==================================



### Install Docker Desktop (One-Time)

* https://docs.docker.com/desktop/install/mac-install/


### Install Localstack (One-Time)

* >pip install --upgrade localstack
* >localstack --version


### Add LOCALSTACK_ENDPOINT_URL to Your .env File (One-Time)

* Find the value in the sample.env file.  Copy and uncomment it into your .env file

### Run with Localstack (Recurring)

#### Start Docker Desktop and localstack image

* Open Docker Desktop from Finder
* Images->Local->localstack/localstack click on start button on right hand side


#### Start Localstack

* From your project directory in a separate terminal window, either:
* >localstack start
* >pipenv run localstack start

#### Proceed Normally

Assuming you followed all these steps and nothing went wrong, you should be running with localstack for SNS now.
You should be able to send an SMS message in the UI and observe it in the dashboard moving from Pending to Delivered
over a period of five minutes.  And you should not receive a text message.

