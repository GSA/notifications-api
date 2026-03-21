"""
Render.com configuration adapter.

Reads database, Redis, and AWS credentials from standard environment variables
provided by Render services and manual env var configuration.

This module mirrors the interface of cloudfoundry_config.py so that config.py
can use either one depending on the runtime environment.
"""

import json
from os import getenv


class RenderConfig:
    def __init__(self):
        self._empty_bucket_credentials = {
            "bucket": "",
            "access_key_id": "",  # nosec B105
            "secret_access_key": "",  # nosec B105
            "region": "",
        }

    @property
    def database_url(self):
        url = getenv("DATABASE_URL", "")
        # Render uses postgres:// but SQLAlchemy requires postgresql://
        return url.replace("postgres://", "postgresql://")

    @property
    def redis_url(self):
        return getenv("REDIS_URL")

    def s3_credentials(self, service_name):
        # On Render, S3 credentials come from env vars, not VCAP_SERVICES.
        # The Production config class reads these via _s3_credentials_from_env.
        return self._empty_bucket_credentials

    @property
    def ses_email_domain(self):
        domain_arn = getenv("SES_DOMAIN_ARN", "dev.notify.gov")
        return domain_arn.split("/")[-1]

    @property
    def ses_domain_arn(self):
        return getenv("SES_DOMAIN_ARN", "dev.notify.gov")

    @property
    def ses_region(self):
        return getenv("SES_AWS_REGION", "us-west-2")

    @property
    def ses_access_key(self):
        return getenv("SES_AWS_ACCESS_KEY_ID")

    @property
    def ses_secret_key(self):
        return getenv("SES_AWS_SECRET_ACCESS_KEY")

    @property
    def sns_access_key(self):
        return getenv("SNS_AWS_ACCESS_KEY_ID")

    @property
    def sns_secret_key(self):
        return getenv("SNS_AWS_SECRET_ACCESS_KEY")

    @property
    def sns_region(self):
        return getenv("SNS_AWS_REGION", "us-west-2")

    @property
    def sns_topic_arns(self):
        # On Render, SNS topic ARNs are not auto-discovered from VCAP_SERVICES.
        # Set SNS_TOPIC_ARNS as a JSON array env var, e.g.:
        #   '["arn:aws:sns:us-west-2:123456:bounce","arn:aws:sns:us-west-2:123456:complaint","arn:aws:sns:us-west-2:123456:delivery"]'
        raw = getenv("SNS_TOPIC_ARNS")
        if raw:
            return json.loads(raw)
        return []
