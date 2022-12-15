import json
from datetime import timedelta
from os import getenv

from celery.schedules import crontab
from kombu import Exchange, Queue

from app.cloudfoundry_config import cloud_config


class QueueNames(object):
    PERIODIC = 'periodic-tasks'
    PRIORITY = 'priority-tasks'
    DATABASE = 'database-tasks'
    SEND_SMS = 'send-sms-tasks'
    SEND_EMAIL = 'send-email-tasks'
    RESEARCH_MODE = 'research-mode-tasks'
    REPORTING = 'reporting-tasks'
    JOBS = 'job-tasks'
    RETRY = 'retry-tasks'
    NOTIFY = 'notify-internal-tasks'
    PROCESS_FTP = 'process-ftp-tasks'
    CREATE_LETTERS_PDF = 'create-letters-pdf-tasks'
    CALLBACKS = 'service-callbacks'
    CALLBACKS_RETRY = 'service-callbacks-retry'
    LETTERS = 'letter-tasks'
    SMS_CALLBACKS = 'sms-callbacks'
    ANTIVIRUS = 'antivirus-tasks'
    SANITISE_LETTERS = 'sanitise-letter-tasks'
    SAVE_API_EMAIL = 'save-api-email-tasks'
    SAVE_API_SMS = 'save-api-sms-tasks'

    @staticmethod
    def all_queues():
        return [
            QueueNames.PRIORITY,
            QueueNames.PERIODIC,
            QueueNames.DATABASE,
            QueueNames.SEND_SMS,
            QueueNames.SEND_EMAIL,
            QueueNames.RESEARCH_MODE,
            QueueNames.REPORTING,
            QueueNames.JOBS,
            QueueNames.RETRY,
            QueueNames.NOTIFY,
            QueueNames.CREATE_LETTERS_PDF,
            QueueNames.CALLBACKS,
            QueueNames.CALLBACKS_RETRY,
            QueueNames.LETTERS,
            QueueNames.SMS_CALLBACKS,
            QueueNames.SAVE_API_EMAIL,
            QueueNames.SAVE_API_SMS,
        ]


class TaskNames(object):
    PROCESS_INCOMPLETE_JOBS = 'process-incomplete-jobs'
    ZIP_AND_SEND_LETTER_PDFS = 'zip-and-send-letter-pdfs'
    SCAN_FILE = 'scan-file'
    SANITISE_LETTER = 'sanitise-and-upload-letter'
    CREATE_PDF_FOR_TEMPLATED_LETTER = 'create-pdf-for-templated-letter'
    RECREATE_PDF_FOR_PRECOMPILED_LETTER = 'recreate-pdf-for-precompiled-letter'


class Config(object):
    NOTIFY_APP_NAME = 'api'
    NOTIFY_ENVIRONMENT = getenv('NOTIFY_ENVIRONMENT', 'development')
    # URL of admin app
    ADMIN_BASE_URL = getenv('ADMIN_BASE_URL', 'http://localhost:6012')
    # URL of api app (on AWS this is the internal api endpoint)
    API_HOST_NAME = getenv('API_HOST_NAME', 'http://localhost:6011')

    # Credentials
    # secrets that internal apps, such as the admin app or document download, must use to authenticate with the API
    # ADMIN_CLIENT_ID is called ADMIN_CLIENT_USER_NAME in api repo, they should match
    ADMIN_CLIENT_ID = getenv('ADMIN_CLIENT_ID', 'notify-admin')
    INTERNAL_CLIENT_API_KEYS = json.loads(
        getenv(
            'INTERNAL_CLIENT_API_KEYS',
            ('{"%s":["%s"]}' % (ADMIN_CLIENT_ID, getenv('ADMIN_CLIENT_SECRET')))
            )
    )
    ALLOW_EXPIRED_API_TOKEN = False
    # encyption secret/salt
    SECRET_KEY = getenv('SECRET_KEY')
    DANGEROUS_SALT = getenv('DANGEROUS_SALT')
    ROUTE_SECRET_KEY_1 = getenv('ROUTE_SECRET_KEY_1', 'dev-route-secret-key-1')
    ROUTE_SECRET_KEY_2 = getenv('ROUTE_SECRET_KEY_2', 'dev-route-secret-key-2')

    # DB settings
    SQLALCHEMY_DATABASE_URI = cloud_config.database_url
    SQLALCHEMY_RECORD_QUERIES = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_SIZE = int(getenv('SQLALCHEMY_POOL_SIZE', 5))
    SQLALCHEMY_POOL_TIMEOUT = 30
    SQLALCHEMY_POOL_RECYCLE = 300
    SQLALCHEMY_STATEMENT_TIMEOUT = 1200
    PAGE_SIZE = 50
    API_PAGE_SIZE = 250
    REDIS_URL = cloud_config.redis_url
    REDIS_ENABLED = getenv('REDIS_ENABLED', '0') == '1'
    EXPIRE_CACHE_TEN_MINUTES = 600
    EXPIRE_CACHE_EIGHT_DAYS = 8 * 24 * 60 * 60

    # AWS Settings
    AWS_REGION = getenv('AWS_REGION')
    AWS_PINPOINT_REGION = getenv("AWS_PINPOINT_REGION")
    AWS_US_TOLL_FREE_NUMBER = getenv("AWS_US_TOLL_FREE_NUMBER")
    # Whether to ignore POSTs from SNS for replies to SMS we sent
    RECEIVE_INBOUND_SMS = False
    NOTIFY_EMAIL_DOMAIN = getenv('NOTIFY_EMAIL_DOMAIN', 'notify.sandbox.10x.gsa.gov')
    SES_STUB_URL = None  # TODO: set to a URL in env and remove this to use a stubbed SES service
    # AWS SNS topics for delivery receipts
    VALIDATE_SNS_TOPICS = True
    VALID_SNS_TOPICS = ['notify_test_bounce', 'notify_test_success', 'notify_test_complaint', 'notify_test_sms_inbound']

    # SMS config to be cleaned up during https://github.com/GSA/notifications-api/issues/7
    # MMG API Key
    MMG_API_KEY = getenv('MMG_API_KEY', 'placeholder')
    # Firetext API Key
    FIRETEXT_API_KEY = getenv("FIRETEXT_API_KEY", "placeholder")
    FIRETEXT_INTERNATIONAL_API_KEY = getenv("FIRETEXT_INTERNATIONAL_API_KEY", "placeholder")
    # these should always add up to 100%
    SMS_PROVIDER_RESTING_POINTS = {
        'sns': 100,
        'mmg': 0,
        'firetext': 0
    }
    FIRETEXT_INBOUND_SMS_AUTH = json.loads(getenv('FIRETEXT_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_AUTH = json.loads(getenv('MMG_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_USERNAME = json.loads(getenv('MMG_INBOUND_SMS_USERNAME', '[]'))
    MMG_URL = getenv("MMG_URL", "https://api.mmg.co.uk/jsonv2a/api.php")
    FIRETEXT_URL = getenv("FIRETEXT_URL", "https://www.firetext.co.uk/api/sendsms/json")

    # Zendesk
    ZENDESK_API_KEY = getenv('ZENDESK_API_KEY')

    # Logging
    DEBUG = False

    # Monitoring
    CRONITOR_ENABLED = False
    CRONITOR_KEYS = json.loads(getenv('CRONITOR_KEYS', '{}'))
    STATSD_HOST = getenv('STATSD_HOST')
    STATSD_PORT = 8125
    STATSD_ENABLED = bool(STATSD_HOST)

    # Antivirus
    ANTIVIRUS_ENABLED = getenv('ANTIVIRUS_ENABLED', '1') == '1'

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200  # 3 days
    INVITATION_EXPIRATION_DAYS = 2
    TEST_MESSAGE_FILENAME = 'Test message'
    ONE_OFF_MESSAGE_FILENAME = 'Report'
    MAX_VERIFY_CODE_COUNT = 5
    MAX_FAILED_LOGIN_COUNT = 10
    API_RATE_LIMIT_ENABLED = True

    # be careful increasing this size without being sure that we won't see slowness in pysftp
    MAX_LETTER_PDF_ZIP_FILESIZE = 40 * 1024 * 1024  # 40mb
    MAX_LETTER_PDF_COUNT_PER_ZIP = 500

    NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
    NOTIFY_USER_ID = '6af522d0-2915-4e52-83a3-3690455a5fe6'
    INVITATION_EMAIL_TEMPLATE_ID = '4f46df42-f795-4cc4-83bb-65ca312f49cc'
    SMS_CODE_TEMPLATE_ID = '36fb0730-6259-4da1-8a80-c8de22ad4246'
    EMAIL_2FA_TEMPLATE_ID = '299726d2-dba6-42b8-8209-30e1d66ea164'
    NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID = 'ece42649-22a8-4d06-b87f-d52d5d3f0a27'
    PASSWORD_RESET_TEMPLATE_ID = '474e9242-823b-4f99-813d-ed392e7f1201'  # nosec B105 - this is not a password
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = '0880fbb1-a0c6-46f0-9a8e-36c986381ceb'
    CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID = 'eb4d9930-87ab-4aef-9bce-786762687884'
    SERVICE_NOW_LIVE_TEMPLATE_ID = '618185c6-3636-49cd-b7d2-6f6f5eb3bdde'
    ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID = '203566f0-d835-47c5-aa06-932439c86573'
    TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID = 'c73f1d71-4049-46d5-a647-d013bdeca3f0'
    TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID = '8a31520f-4751-4789-8ea1-fe54496725eb'
    REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID = 'a42f1d17-9404-46d5-a647-d013bdfca3e1'
    MOU_SIGNER_RECEIPT_TEMPLATE_ID = '4fd2e43c-309b-4e50-8fb8-1955852d9d71'
    MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID = 'c20206d5-bf03-4002-9a90-37d5032d9e84'
    MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID = '522b6657-5ca5-4368-a294-6b527703bd0b'
    NOTIFY_INTERNATIONAL_SMS_SENDER = '18446120782'
    LETTERS_VOLUME_EMAIL_TEMPLATE_ID = '11fad854-fd38-4a7c-bd17-805fb13dfc12'
    NHS_EMAIL_BRANDING_ID = 'a7dc4e56-660b-4db7-8cff-12c37b12b5ea'
    # we only need real email in Live environment (production)
    DVLA_EMAIL_ADDRESSES = json.loads(getenv('DVLA_EMAIL_ADDRESSES', '[]'))

    CELERY = {
        'broker_url': REDIS_URL,
        'broker_transport_options': {
            'visibility_timeout': 310,
        },
        'timezone': getenv("TIMEZONE", 'America/New_York'),
        'imports': [
            'app.celery.tasks',
            'app.celery.scheduled_tasks',
            'app.celery.reporting_tasks',
            'app.celery.nightly_tasks',
        ],
        # this is overriden by the -Q command, but locally, we should read from all queues
        'task_queues': [
            Queue(queue, Exchange('default'), routing_key=queue) for queue in QueueNames.all_queues()
        ],
        'beat_schedule': {
            # app/celery/scheduled_tasks.py
            'run-scheduled-jobs': {
                'task': 'run-scheduled-jobs',
                'schedule': crontab(minute='0,15,30,45'),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'delete-verify-codes': {
                'task': 'delete-verify-codes',
                'schedule': timedelta(minutes=63),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'delete-invitations': {
                'task': 'delete-invitations',
                'schedule': timedelta(minutes=66),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'check-job-status': {
                'task': 'check-job-status',
                'schedule': crontab(),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'tend-providers-back-to-middle': {
                'task': 'tend-providers-back-to-middle',
                'schedule': crontab(minute='*/5'),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'check-for-missing-rows-in-completed-jobs': {
                'task': 'check-for-missing-rows-in-completed-jobs',
                'schedule': crontab(minute='*/10'),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'replay-created-notifications': {
                'task': 'replay-created-notifications',
                'schedule': crontab(minute='0, 15, 30, 45'),
                'options': {'queue': QueueNames.PERIODIC}
            },
            # app/celery/nightly_tasks.py
            'timeout-sending-notifications': {
                'task': 'timeout-sending-notifications',
                'schedule': crontab(hour=0, minute=5),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'create-nightly-billing': {
                'task': 'create-nightly-billing',
                'schedule': crontab(hour=0, minute=15),
                'options': {'queue': QueueNames.REPORTING}
            },
            'create-nightly-notification-status': {
                'task': 'create-nightly-notification-status',
                'schedule': crontab(hour=0, minute=30),  # after 'timeout-sending-notifications'
                'options': {'queue': QueueNames.REPORTING}
            },
            'delete-notifications-older-than-retention': {
                'task': 'delete-notifications-older-than-retention',
                'schedule': crontab(hour=3, minute=0),  # after 'create-nightly-notification-status'
                'options': {'queue': QueueNames.REPORTING}
            },
            'delete-inbound-sms': {
                'task': 'delete-inbound-sms',
                'schedule': crontab(hour=1, minute=40),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'save-daily-notification-processing-time': {
                'task': 'save-daily-notification-processing-time',
                'schedule': crontab(hour=2, minute=0),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'remove_sms_email_jobs': {
                'task': 'remove_sms_email_jobs',
                'schedule': crontab(hour=4, minute=0),
                'options': {'queue': QueueNames.PERIODIC},
            },
            'remove_letter_jobs': {
                'task': 'remove_letter_jobs',
                'schedule': crontab(hour=4, minute=20),
                # since we mark jobs as archived
                'options': {'queue': QueueNames.PERIODIC},
            },
            'check-if-letters-still-in-created': {
                'task': 'check-if-letters-still-in-created',
                'schedule': crontab(day_of_week='mon-fri', hour=7, minute=0),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'check-if-letters-still-pending-virus-check': {
                'task': 'check-if-letters-still-pending-virus-check',
                'schedule': crontab(day_of_week='mon-fri', hour='9,15', minute=0),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'check-for-services-with-high-failure-rates-or-sending-to-tv-numbers': {
                'task': 'check-for-services-with-high-failure-rates-or-sending-to-tv-numbers',
                'schedule': crontab(day_of_week='mon-fri', hour=10, minute=30),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'raise-alert-if-letter-notifications-still-sending': {
                'task': 'raise-alert-if-letter-notifications-still-sending',
                'schedule': crontab(hour=17, minute=00),
                'options': {'queue': QueueNames.PERIODIC}
            },
            # The collate-letter-pdf does assume it is called in an hour that BST does not make a
            # difference to the truncate date which translates to the filename to process
            'collate-letter-pdfs-to-be-sent': {
                'task': 'collate-letter-pdfs-to-be-sent',
                'schedule': crontab(hour=17, minute=50),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'raise-alert-if-no-letter-ack-file': {
                'task': 'raise-alert-if-no-letter-ack-file',
                'schedule': crontab(hour=23, minute=00),
                'options': {'queue': QueueNames.PERIODIC}
            },
            'trigger-link-tests': {
                'task': 'trigger-link-tests',
                'schedule': timedelta(minutes=15),
                'options': {'queue': QueueNames.PERIODIC}
            },
        }
    }

    # we can set celeryd_prefetch_multiplier to be 1 for celery apps which handle only long running tasks
    if getenv('CELERYD_PREFETCH_MULTIPLIER'):
        CELERY['worker_prefetch_multiplier'] = getenv('CELERYD_PREFETCH_MULTIPLIER')

    FROM_NUMBER = 'development'

    SIMULATED_EMAIL_ADDRESSES = (
        'simulate-delivered@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk',
        'simulate-delivered-3@notifications.service.gov.uk',
    )
    SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')

    FREE_SMS_TIER_FRAGMENT_COUNT = 250000

    HIGH_VOLUME_SERVICE = json.loads(getenv('HIGH_VOLUME_SERVICE', '[]'))

    TEMPLATE_PREVIEW_API_HOST = getenv('TEMPLATE_PREVIEW_API_HOST', 'http://localhost:6013')
    TEMPLATE_PREVIEW_API_KEY = getenv('TEMPLATE_PREVIEW_API_KEY', 'my-secret-key')

    DOCUMENT_DOWNLOAD_API_HOST = getenv('DOCUMENT_DOWNLOAD_API_HOST', 'http://localhost:7000')
    DOCUMENT_DOWNLOAD_API_KEY = getenv('DOCUMENT_DOWNLOAD_API_KEY', 'auth-token')


def _default_s3_credentials(bucket_name):
    return {
        'bucket': bucket_name,
        'access_key_id': getenv('AWS_ACCESS_KEY_ID'),
        'secret_access_key': getenv('AWS_SECRET_ACCESS_KEY'),
        'region': getenv('AWS_REGION')
    }


class Development(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False
    DVLA_EMAIL_ADDRESSES = ['success@simulator.amazonses.com']

    # Buckets
    CSV_UPLOAD_BUCKET = _default_s3_credentials('local-notifications-csv-upload')
    CONTACT_LIST_BUCKET = _default_s3_credentials('local-contact-list')

    # credential overrides
    DANGEROUS_SALT = 'development-notify-salt'
    SECRET_KEY = 'dev-notify-secret-key'  # nosec B105 - this is only used in development
    INTERNAL_CLIENT_API_KEYS = {Config.ADMIN_CLIENT_ID: ['dev-notify-secret-key']}
    ALLOW_EXPIRED_API_TOKEN = getenv('ALLOW_EXPIRED_API_TOKEN', '0') == '1'


class Test(Development):
    FROM_NUMBER = 'testing'
    TESTING = True
    ANTIVIRUS_ENABLED = True
    DVLA_EMAIL_ADDRESSES = ['success@simulator.amazonses.com', 'success+2@simulator.amazonses.com']

    FIRETEXT_INBOUND_SMS_AUTH = ['testkey']
    MMG_INBOUND_SMS_AUTH = ['testkey']
    MMG_INBOUND_SMS_USERNAME = ['username']

    HIGH_VOLUME_SERVICE = [
        '941b6f9a-50d7-4742-8d50-f365ca74bf27',
        '63f95b86-2d19-4497-b8b2-ccf25457df4e',
        '7e5950cb-9954-41f5-8376-962b8c8555cf',
        '10d1b9c9-0072-4fa9-ae1c-595e333841da',
    ]

    CSV_UPLOAD_BUCKET = _default_s3_credentials('test-notifications-csv-upload')
    CONTACT_LIST_BUCKET = _default_s3_credentials('test-contact-list')

    # this is overriden in CI
    SQLALCHEMY_DATABASE_URI = getenv('SQLALCHEMY_DATABASE_TEST_URI')

    CELERY = {
        **Config.CELERY,
        'broker_url': 'you-forgot-to-mock-celery-in-your-tests://'
    }

    TEMPLATE_PREVIEW_API_HOST = 'http://localhost:9999'


class Production(Config):
    # buckets
    CSV_UPLOAD_BUCKET = cloud_config.s3_credentials(
        f"notify-api-csv-upload-bucket-{Config.NOTIFY_ENVIRONMENT}")
    CONTACT_LIST_BUCKET = cloud_config.s3_credentials(
        f"notify-api-contact-list-bucket-{Config.NOTIFY_ENVIRONMENT}")

    FROM_NUMBER = 'US Notify'
    CRONITOR_ENABLED = True


class Staging(Production):
    pass


class Demo(Production):
    pass


configs = {
    'development': Development,
    'test': Test,
    'staging': Staging,
    'demo': Demo,
    'sandbox': Staging,
    'production': Production
}
