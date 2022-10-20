import json
import os
from datetime import timedelta

from celery.schedules import crontab
from kombu import Exchange, Queue

if os.environ.get('VCAP_SERVICES'):
    # on cloudfoundry, config is a json blob in VCAP_SERVICES - unpack it, and populate
    # standard environment variables from it
    from app.cloudfoundry_config import extract_cloudfoundry_config

    extract_cloudfoundry_config()


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
    # URL of admin app
    ADMIN_BASE_URL = os.environ.get('ADMIN_BASE_URL')

    # URL of api app (on AWS this is the internal api endpoint)
    API_HOST_NAME = os.environ.get('API_HOST_NAME')

    # secrets that internal apps, such as the admin app or document download, must use to authenticate with the API
    ADMIN_CLIENT_ID = 'notify-admin'

    INTERNAL_CLIENT_API_KEYS = json.loads(
        os.environ.get('INTERNAL_CLIENT_API_KEYS', '{"notify-admin":["dev-notify-secret-key"]}')
    ) # TODO: handled by varsfile?

    # encyption secret/salt
    ADMIN_CLIENT_SECRET = os.environ.get('ADMIN_CLIENT_SECRET')
    SECRET_KEY = os.environ.get('SECRET_KEY')
    DANGEROUS_SALT = os.environ.get('DANGEROUS_SALT')

    # DB conection string
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')

    # AWS SMS
    AWS_PINPOINT_REGION = os.environ.get("AWS_PINPOINT_REGION")
    AWS_US_TOLL_FREE_NUMBER = os.environ.get("AWS_US_TOLL_FREE_NUMBER")

    # MMG API Key
    MMG_API_KEY = os.environ.get('MMG_API_KEY', 'placeholder')

    # Firetext API Key
    FIRETEXT_API_KEY = os.environ.get("FIRETEXT_API_KEY", "placeholder")
    FIRETEXT_INTERNATIONAL_API_KEY = os.environ.get("FIRETEXT_INTERNATIONAL_API_KEY", "placeholder")
    
    # Whether to ignore POSTs from SNS for replies to SMS we sent
    RECEIVE_INBOUND_SMS = False

    # Use notify.sandbox.10x sending domain unless overwritten by environment
    NOTIFY_EMAIL_DOMAIN = 'notify.sandbox.10x.gsa.gov'
    
    # AWS SNS topics for delivery receipts
    VALIDATE_SNS_TOPICS = True
    VALID_SNS_TOPICS = ['notify_test_bounce', 'notify_test_success', 'notify_test_complaint', 'notify_test_sms_inbound']

    # URL of redis instance
    REDIS_URL = os.environ.get('REDIS_URL')
    REDIS_ENABLED = os.environ.get('REDIS_ENABLED')
    EXPIRE_CACHE_TEN_MINUTES = 600
    EXPIRE_CACHE_EIGHT_DAYS = 8 * 24 * 60 * 60

    # Zendesk
    ZENDESK_API_KEY = os.environ.get('ZENDESK_API_KEY')

    # Logging
    DEBUG = False
    NOTIFY_LOG_PATH = os.environ.get('NOTIFY_LOG_PATH')

    # Cronitor
    CRONITOR_ENABLED = False
    CRONITOR_KEYS = json.loads(os.environ.get('CRONITOR_KEYS', '{}'))

    # Antivirus
    ANTIVIRUS_ENABLED = True

    ###########################
    # Default config values ###
    ###########################

    NOTIFY_ENVIRONMENT = 'development'
    AWS_REGION = 'us-west-2'
    INVITATION_EXPIRATION_DAYS = 2
    NOTIFY_APP_NAME = 'api'
    SQLALCHEMY_RECORD_QUERIES = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_SIZE = int(os.environ.get('SQLALCHEMY_POOL_SIZE', 5))
    SQLALCHEMY_POOL_TIMEOUT = 30
    SQLALCHEMY_POOL_RECYCLE = 300
    SQLALCHEMY_STATEMENT_TIMEOUT = 1200
    PAGE_SIZE = 50
    API_PAGE_SIZE = 250
    TEST_MESSAGE_FILENAME = 'Test message'
    ONE_OFF_MESSAGE_FILENAME = 'Report'
    MAX_VERIFY_CODE_COUNT = 5
    MAX_FAILED_LOGIN_COUNT = 10

    SES_STUB_URL = None  # TODO: set to a URL in env and remove this to use a stubbed SES service

    # be careful increasing this size without being sure that we won't see slowness in pysftp
    MAX_LETTER_PDF_ZIP_FILESIZE = 40 * 1024 * 1024  # 40mb
    MAX_LETTER_PDF_COUNT_PER_ZIP = 500

    CHECK_PROXY_HEADER = False

    # these should always add up to 100%
    SMS_PROVIDER_RESTING_POINTS = {
        'mmg': 50,
        'firetext': 50
    }

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
    DVLA_EMAIL_ADDRESSES = json.loads(os.environ.get('DVLA_EMAIL_ADDRESSES', '[]'))

    CELERY = {
        'broker_url': REDIS_URL,
        'broker_transport_options': {
            'visibility_timeout': 310,
        },
        'timezone': 'Europe/London',
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
            'switch-current-sms-provider-on-slow-delivery': {
                'task': 'switch-current-sms-provider-on-slow-delivery',
                'schedule': crontab(),  # Every minute
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
    if os.environ.get('CELERYD_PREFETCH_MULTIPLIER'):
        CELERY['worker_prefetch_multiplier'] = os.environ.get('CELERYD_PREFETCH_MULTIPLIER')

    FROM_NUMBER = 'development'

    STATSD_HOST = os.environ.get('STATSD_HOST')
    STATSD_PORT = 8125
    STATSD_ENABLED = bool(STATSD_HOST)

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200  # 3 days

    SIMULATED_EMAIL_ADDRESSES = (
        'simulate-delivered@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk',
        'simulate-delivered-3@notifications.service.gov.uk',
    )

    SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')

    FREE_SMS_TIER_FRAGMENT_COUNT = 250000

    SMS_INBOUND_WHITELIST = json.loads(os.environ.get('SMS_INBOUND_WHITELIST', '[]'))
    FIRETEXT_INBOUND_SMS_AUTH = json.loads(os.environ.get('FIRETEXT_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_AUTH = json.loads(os.environ.get('MMG_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_USERNAME = json.loads(os.environ.get('MMG_INBOUND_SMS_USERNAME', '[]'))
    ROUTE_SECRET_KEY_1 = os.environ.get('ROUTE_SECRET_KEY_1', 'dev-route-secret-key-1')
    ROUTE_SECRET_KEY_2 = os.environ.get('ROUTE_SECRET_KEY_2', 'dev-route-secret-key-2')

    HIGH_VOLUME_SERVICE = json.loads(os.environ.get('HIGH_VOLUME_SERVICE', '[]'))

    TEMPLATE_PREVIEW_API_HOST = os.environ.get('TEMPLATE_PREVIEW_API_HOST', 'http://localhost:6013')
    TEMPLATE_PREVIEW_API_KEY = os.environ.get('TEMPLATE_PREVIEW_API_KEY', 'my-secret-key')

    DOCUMENT_DOWNLOAD_API_HOST = os.environ.get('DOCUMENT_DOWNLOAD_API_HOST', 'http://localhost:7000')
    DOCUMENT_DOWNLOAD_API_KEY = os.environ.get('DOCUMENT_DOWNLOAD_API_KEY', 'auth-token')

    # these environment vars aren't defined in the manifest so to set them on paas use `cf set-env`
    MMG_URL = os.environ.get("MMG_URL", "https://api.mmg.co.uk/jsonv2a/api.php")
    FIRETEXT_URL = os.environ.get("FIRETEXT_URL", "https://www.firetext.co.uk/api/sendsms/json")

    AWS_REGION = 'us-west-2'


######################
# Config overrides ###
######################

class Development(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False

    REDIS_ENABLED = os.environ.get('REDIS_ENABLED')

    CSV_UPLOAD_BUCKET_NAME = 'local-notifications-csv-upload'
    CSV_UPLOAD_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    CSV_UPLOAD_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    CSV_UPLOAD_REGION = os.environ.get('AWS_REGION', 'us-west-2')
    CONTACT_LIST_BUCKET_NAME = 'local-contact-list'
    CONTACT_LIST_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
    CONTACT_LIST_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    CONTACT_LIST_REGION = os.environ.get('AWS_REGION', 'us-west-2')
    # TEST_LETTERS_BUCKET_NAME = 'development-test-letters'
    # DVLA_RESPONSE_BUCKET_NAME = 'notify.tools-ftp'
    # LETTERS_PDF_BUCKET_NAME = 'development-letters-pdf'
    # LETTERS_SCAN_BUCKET_NAME = 'development-letters-scan'
    # INVALID_PDF_BUCKET_NAME = 'development-letters-invalid-pdf'
    # TRANSIENT_UPLOADED_LETTERS = 'development-transient-uploaded-letters'
    # LETTER_SANITISE_BUCKET_NAME = 'development-letters-sanitise'

    # INTERNAL_CLIENT_API_KEYS = {
    #     Config.ADMIN_CLIENT_ID: ['dev-notify-secret-key'],
    # }

    SECRET_KEY = 'dev-notify-secret-key' # nosec B105 - this is only used in development
    DANGEROUS_SALT = 'dev-notify-salt'

    MMG_INBOUND_SMS_AUTH = ['testkey']
    MMG_INBOUND_SMS_USERNAME = ['username']

    NOTIFY_ENVIRONMENT = 'development'
    NOTIFY_LOG_PATH = 'application.log'

    NOTIFY_EMAIL_DOMAIN = os.getenv('NOTIFY_EMAIL_DOMAIN', 'notify.sandbox.10x.gsa.gov')

    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI', 'postgresql://postgres:chummy@db:5432/notification_api')

    ANTIVIRUS_ENABLED = os.environ.get('ANTIVIRUS_ENABLED') == '1'

    ADMIN_BASE_URL = os.getenv('ADMIN_BASE_URL', 'http://localhost:6012')

    API_HOST_NAME = os.getenv('API_HOST_NAME', 'http://localhost:6011')

    API_RATE_LIMIT_ENABLED = True
    DVLA_EMAIL_ADDRESSES = ['success@simulator.amazonses.com']


class Test(Development):
    NOTIFY_EMAIL_DOMAIN = 'test.notify.com'
    FROM_NUMBER = 'testing'
    NOTIFY_ENVIRONMENT = 'test'
    TESTING = True

    HIGH_VOLUME_SERVICE = [
        '941b6f9a-50d7-4742-8d50-f365ca74bf27',
        '63f95b86-2d19-4497-b8b2-ccf25457df4e',
        '7e5950cb-9954-41f5-8376-962b8c8555cf',
        '10d1b9c9-0072-4fa9-ae1c-595e333841da',
    ]

    CSV_UPLOAD_BUCKET_NAME = 'test-notifications-csv-upload'
    CONTACT_LIST_BUCKET_NAME = 'test-contact-list'
    # TEST_LETTERS_BUCKET_NAME = 'test-test-letters'
    # DVLA_RESPONSE_BUCKET_NAME = 'test.notify.com-ftp'
    # LETTERS_PDF_BUCKET_NAME = 'test-letters-pdf'
    # LETTERS_SCAN_BUCKET_NAME = 'test-letters-scan'
    # INVALID_PDF_BUCKET_NAME = 'test-letters-invalid-pdf'
    # TRANSIENT_UPLOADED_LETTERS = 'test-transient-uploaded-letters'
    # LETTER_SANITISE_BUCKET_NAME = 'test-letters-sanitise'

    # this is overriden in CI
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_TEST_URI', 'postgresql://postgres:chummy@db:5432/test_notification_api')

    CELERY = {
        **Config.CELERY,
        'broker_url': 'you-forgot-to-mock-celery-in-your-tests://'
    }

    ANTIVIRUS_ENABLED = True

    API_RATE_LIMIT_ENABLED = True
    API_HOST_NAME = "http://localhost:6011"

    SMS_INBOUND_WHITELIST = ['203.0.113.195']
    FIRETEXT_INBOUND_SMS_AUTH = ['testkey']
    TEMPLATE_PREVIEW_API_HOST = 'http://localhost:9999'

    MMG_URL = 'https://example.com/mmg'
    FIRETEXT_URL = 'https://example.com/firetext'

    DVLA_EMAIL_ADDRESSES = ['success@simulator.amazonses.com', 'success+2@simulator.amazonses.com']


class Preview(Config):
    NOTIFY_EMAIL_DOMAIN = 'notify.works'
    NOTIFY_ENVIRONMENT = 'preview'
    CSV_UPLOAD_BUCKET_NAME = 'preview-notifications-csv-upload'
    CONTACT_LIST_BUCKET_NAME = 'preview-contact-list'
    # TEST_LETTERS_BUCKET_NAME = 'preview-test-letters'
    # DVLA_RESPONSE_BUCKET_NAME = 'notify.works-ftp'
    # LETTERS_PDF_BUCKET_NAME = 'preview-letters-pdf'
    # LETTERS_SCAN_BUCKET_NAME = 'preview-letters-scan'
    # INVALID_PDF_BUCKET_NAME = 'preview-letters-invalid-pdf'
    # TRANSIENT_UPLOADED_LETTERS = 'preview-transient-uploaded-letters'
    # LETTER_SANITISE_BUCKET_NAME = 'preview-letters-sanitise'
    FROM_NUMBER = 'preview'
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = False


class Staging(Config):
    NOTIFY_EMAIL_DOMAIN = 'staging-notify.works'
    NOTIFY_ENVIRONMENT = 'staging'
    CSV_UPLOAD_BUCKET_NAME = 'staging-notifications-csv-upload'
    CONTACT_LIST_BUCKET_NAME = 'staging-contact-list'
    # TEST_LETTERS_BUCKET_NAME = 'staging-test-letters'
    # DVLA_RESPONSE_BUCKET_NAME = 'staging-notify.works-ftp'
    # LETTERS_PDF_BUCKET_NAME = 'staging-letters-pdf'
    # LETTERS_SCAN_BUCKET_NAME = 'staging-letters-scan'
    # INVALID_PDF_BUCKET_NAME = 'staging-letters-invalid-pdf'
    # TRANSIENT_UPLOADED_LETTERS = 'staging-transient-uploaded-letters'
    # LETTER_SANITISE_BUCKET_NAME = 'staging-letters-sanitise'
    FROM_NUMBER = 'stage'
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True


class Live(Config):
    NOTIFY_ENVIRONMENT = 'live'
    # buckets
    CSV_UPLOAD_BUCKET_NAME = os.environ.get('CSV_UPLOAD_BUCKET_NAME', 'notifications-prototype-csv-upload') # created in gsa sandbox
    CSV_UPLOAD_ACCESS_KEY = os.environ.get('CSV_UPLOAD_ACCESS_KEY')
    CSV_UPLOAD_SECRET_KEY = os.environ.get('CSV_UPLOAD_SECRET_KEY')
    CSV_UPLOAD_REGION = os.environ.get('CSV_UPLOAD_REGION')
    CONTACT_LIST_BUCKET_NAME = os.environ.get('CONTACT_LIST_BUCKET_NAME', 'notifications-prototype-contact-list-upload') # created in gsa sandbox
    CONTACT_LIST_ACCESS_KEY = os.environ.get('CONTACT_LIST_ACCESS_KEY')
    CONTACT_LIST_SECRET_KEY = os.environ.get('CONTACT_LIST_SECRET_KEY')
    CONTACT_LIST_REGION = os.environ.get('CONTACT_LIST_REGION')
    # TODO: verify below buckets only used for letters
    # TEST_LETTERS_BUCKET_NAME = 'production-test-letters' # not created in gsa sandbox
    # DVLA_RESPONSE_BUCKET_NAME = 'notifications.service.gov.uk-ftp' # not created in gsa sandbox
    # LETTERS_PDF_BUCKET_NAME = 'production-letters-pdf' # not created in gsa sandbox
    # LETTERS_SCAN_BUCKET_NAME = 'production-letters-scan' # not created in gsa sandbox
    # INVALID_PDF_BUCKET_NAME = 'production-letters-invalid-pdf' # not created in gsa sandbox
    # TRANSIENT_UPLOADED_LETTERS = 'production-transient-uploaded-letters' # not created in gsa sandbox
    # LETTER_SANITISE_BUCKET_NAME = 'production-letters-sanitise' # not created in gsa sandbox

    FROM_NUMBER = 'US Notify'
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True
    SES_STUB_URL = None
    CRONITOR_ENABLED = True

    # DEBUG = True
    REDIS_ENABLED = os.environ.get('REDIS_ENABLED')

    NOTIFY_LOG_PATH = os.environ.get('NOTIFY_LOG_PATH', 'application.log')


class CloudFoundryConfig(Config):
    pass


# CloudFoundry sandbox
class Sandbox(CloudFoundryConfig):
    NOTIFY_EMAIL_DOMAIN = 'notify.works'
    NOTIFY_ENVIRONMENT = 'sandbox'
    CSV_UPLOAD_BUCKET_NAME = 'cf-sandbox-notifications-csv-upload'
    CONTACT_LIST_BUCKET_NAME = 'cf-sandbox-contact-list'
    # LETTERS_PDF_BUCKET_NAME = 'cf-sandbox-letters-pdf'
    # TEST_LETTERS_BUCKET_NAME = 'cf-sandbox-test-letters'
    # DVLA_RESPONSE_BUCKET_NAME = 'notify.works-ftp'
    # LETTERS_PDF_BUCKET_NAME = 'cf-sandbox-letters-pdf'
    # LETTERS_SCAN_BUCKET_NAME = 'cf-sandbox-letters-scan'
    # INVALID_PDF_BUCKET_NAME = 'cf-sandbox-letters-invalid-pdf'
    FROM_NUMBER = 'sandbox'


configs = {
    'development': Development,
    'test': Test,
    'live': Live,
    'production': Live,
    'staging': Staging,
    'preview': Preview,
    'sandbox': Sandbox
}
