import json
import os


def extract_cloudfoundry_config():
    vcap_services = json.loads(os.environ['VCAP_SERVICES'])

    # Postgres config
    os.environ['SQLALCHEMY_DATABASE_URI'] = vcap_services['aws-rds'][0]['credentials']['uri'].replace('postgres',
                                                                                                      'postgresql')
    # Redis config
    os.environ['REDIS_URL'] = vcap_services['aws-elasticache-redis'][0]['credentials']['uri']
