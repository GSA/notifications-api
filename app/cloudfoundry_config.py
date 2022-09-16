import json
import os


def find_by_service_name(services, service_name):
    for i in range(len(services)):
        if services[i]['name'] == service_name:
            return services[i]
    return None

def extract_cloudfoundry_config():
    vcap_services = json.loads(os.environ['VCAP_SERVICES'])

    # Postgres config
    os.environ['SQLALCHEMY_DATABASE_URI'] = vcap_services['aws-rds'][0]['credentials']['uri'].replace('postgres',
                                                                                                      'postgresql')
    # Redis config
    os.environ['REDIS_URL'] = vcap_services['aws-elasticache-redis'][0]['credentials']['uri']

    # CSV Upload Bucket Name
    csv_bucket_service = find_by_service_name(vcap_services['s3'], f"notifications-api-csv-upload-bucket-{os.environ['DEPLOY_ENV']}")
    if csv_bucket_service:
        os.environ['CSV_UPLOAD_BUCKET_NAME'] = csv_bucket_service['credentials']['bucket']

    # Contact List Bucket Name
    contact_bucket_service = find_by_service_name(vcap_services['s3'], f"notifications-api-contact-list-bucket-{os.environ['DEPLOY_ENV']}")
    if contact_bucket_service:
        os.environ['CONTACT_LIST_BUCKET_NAME'] = contact_bucket_service['credentials']['bucket']
