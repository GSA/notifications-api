import json
from os import getenv


class CloudfoundryConfig:
    def __init__(self):
        self.parsed_services = json.loads(getenv('VCAP_SERVICES') or '{}')
        buckets = self.parsed_services.get('s3') or []
        self.s3_buckets = {bucket['name']: bucket['credentials'] for bucket in buckets}
        self._empty_bucket_credentials = {
            'bucket': '',
            'access_key_id': '',
            'secret_access_key': '',
            'region': ''
        }

    @property
    def database_url(self):
        return getenv('DATABASE_URL', '').replace('postgres://', 'postgresql://')

    @property
    def redis_url(self):
        try:
            return self.parsed_services['aws-elasticache-redis'][0]['credentials']['uri'].replace(
                'redis://',
                'rediss://'
            )
        except KeyError:
            return getenv('REDIS_URL')

    def s3_credentials(self, service_name):
        return self.s3_buckets.get(service_name) or self._empty_bucket_credentials


cloud_config = CloudfoundryConfig()
