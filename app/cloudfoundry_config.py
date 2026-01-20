import json
from os import getenv


class CloudfoundryConfig:
    def __init__(self):
        self.parsed_services = json.loads(getenv("VCAP_SERVICES") or "{}")
        buckets = self.parsed_services.get("s3") or []
        self.s3_buckets = {bucket["name"]: bucket["credentials"] for bucket in buckets}
        self._empty_bucket_credentials = {
            "bucket": "",
            "access_key_id": "",   # pragma: allowlist secret
            "secret_access_key": "",   # pragma: allowlist secret
            "region": "",
        }

    @property
    def database_url(self):
        return getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")

    @property
    def redis_url(self):
        try:
            return self.parsed_services["aws-elasticache-redis"][0]["credentials"][
                "uri"
            ].replace("redis://", "rediss://")
        except KeyError:
            return getenv("REDIS_URL")

    def s3_credentials(self, service_name):
        return self.s3_buckets.get(service_name) or self._empty_bucket_credentials

    @property
    def ses_email_domain(self):
        try:
            domain_arn = self._ses_credentials("domain_arn")
        except KeyError:
            domain_arn = getenv("SES_DOMAIN_ARN", "dev.notify.gov")
        return domain_arn.split("/")[-1]

    # TODO remove this after notifications-api #258
    @property
    def ses_domain_arn(self):
        try:
            domain_arn = self._ses_credentials("domain_arn")
        except KeyError:
            domain_arn = getenv("SES_DOMAIN_ARN", "dev.notify.gov")
        return domain_arn

    @property
    def ses_region(self):
        try:
            return self._ses_credentials("region")
        except KeyError:
            return getenv("SES_AWS_REGION", "us-west-1")

    @property
    def ses_access_key(self):
        try:
            return self._ses_credentials("smtp_user")
        except KeyError:
            return getenv("SES_AWS_ACCESS_KEY_ID")

    @property
    def ses_secret_key(self):
        try:
            return self._ses_credentials("secret_access_key")
        except KeyError:
            return getenv("SES_AWS_SECRET_ACCESS_KEY")

    @property
    def sns_access_key(self):
        try:
            return self._sns_credentials("aws_access_key_id")
        except KeyError:
            return getenv("SNS_AWS_ACCESS_KEY_ID")

    @property
    def sns_secret_key(self):
        try:
            return self._sns_credentials("aws_secret_access_key")
        except KeyError:
            return getenv("SNS_AWS_SECRET_ACCESS_KEY")

    @property
    def sns_region(self):
        try:
            return self._sns_credentials("region")
        except KeyError:
            return getenv("SNS_AWS_REGION", "us-west-1")

    @property
    def sns_topic_arns(self):
        try:
            return [
                self._ses_credentials("bounce_topic_arn"),
                self._ses_credentials("complaint_topic_arn"),
                self._ses_credentials("delivery_topic_arn"),
            ]
        except KeyError:
            return []

    def _ses_credentials(self, key):
        return self.parsed_services["datagov-smtp"][0]["credentials"][key]

    def _sns_credentials(self, key):
        return self.parsed_services["ttsnotify-sms"][0]["credentials"][key]


cloud_config = CloudfoundryConfig()
