from collections import namedtuple
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import ANY, call

import pytest
from freezegun import freeze_time
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
)

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (
    check_for_missing_rows_in_completed_jobs,
    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers,
    check_if_letters_still_in_created,
    check_if_letters_still_pending_virus_check,
    check_job_status,
    delete_invitations,
    delete_verify_codes,
    replay_created_notifications,
    run_scheduled_jobs,
)
from app.config import QueueNames, TaskNames, Test
from app.dao.jobs_dao import dao_get_job_by_id
from app.models import (
    JOB_STATUS_ERROR,
    JOB_STATUS_FINISHED,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_PENDING_VIRUS_CHECK,
)
from tests.app import load_example_csv
from tests.app.db import create_job, create_notification, create_template


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_db_session, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_db_session, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago')
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_should_update_scheduled_jobs_and_put_on_queue(mocker, sample_template):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    job = create_job(sample_template, job_status='scheduled', scheduled_for=one_minute_in_the_past)

    run_scheduled_jobs()

    updated_job = dao_get_job_by_id(job.id)
    assert updated_job.job_status == 'pending'
    mocked.assert_called_with([str(job.id)], queue="job-tasks")


def test_should_update_all_scheduled_jobs_and_put_on_queue(sample_template, mocker):
    mocked = mocker.patch('app.celery.tasks.process_job.apply_async')

    one_minute_in_the_past = datetime.utcnow() - timedelta(minutes=1)
    ten_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=10)
    twenty_minutes_in_the_past = datetime.utcnow() - timedelta(minutes=20)
    job_1 = create_job(sample_template, job_status='scheduled', scheduled_for=one_minute_in_the_past)
    job_2 = create_job(sample_template, job_status='scheduled', scheduled_for=ten_minutes_in_the_past)
    job_3 = create_job(sample_template, job_status='scheduled', scheduled_for=twenty_minutes_in_the_past)

    run_scheduled_jobs()

    assert dao_get_job_by_id(job_1.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'
    assert dao_get_job_by_id(job_2.id).job_status == 'pending'

    mocked.assert_has_calls([
        call([str(job_3.id)], queue="job-tasks"),
        call([str(job_2.id)], queue="job-tasks"),
        call([str(job_1.id)], queue="job-tasks")
    ])


def test_check_job_status_task_calls_process_incomplete_jobs(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    create_notification(template=sample_template, job=job)
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_calls_process_incomplete_jobs_when_scheduled_job_is_not_complete(
    mocker, sample_template
):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_calls_process_incomplete_jobs_for_pending_scheduled_jobs(
    mocker, sample_template
):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_PENDING)

    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_does_not_call_process_incomplete_jobs_for_non_scheduled_pending_jobs(
    mocker,
    sample_template,
):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        job_status=JOB_STATUS_PENDING
    )
    check_job_status()

    assert not mock_celery.called


def test_check_job_status_task_calls_process_incomplete_jobs_for_multiple_jobs(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(template=sample_template, notification_count=3,
                     created_at=datetime.utcnow() - timedelta(hours=2),
                     scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                     processing_started=datetime.utcnow() - timedelta(minutes=31),
                     job_status=JOB_STATUS_IN_PROGRESS)
    job_2 = create_job(template=sample_template, notification_count=3,
                       created_at=datetime.utcnow() - timedelta(hours=2),
                       scheduled_for=datetime.utcnow() - timedelta(minutes=31),
                       processing_started=datetime.utcnow() - timedelta(minutes=31),
                       job_status=JOB_STATUS_IN_PROGRESS)
    check_job_status()

    mock_celery.assert_called_once_with(
        [[str(job.id), str(job_2.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_only_sends_old_tasks(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=50),
        scheduled_for=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_PENDING
    )
    check_job_status()

    # jobs 2 and 3 were created less than 30 minutes ago, so are not sent to Celery task
    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )


def test_check_job_status_task_sets_jobs_to_error(mocker, sample_template):
    mock_celery = mocker.patch('app.celery.tasks.process_incomplete_jobs.apply_async')
    job = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    job_2 = create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=29),
        job_status=JOB_STATUS_IN_PROGRESS
    )
    check_job_status()

    # job 2 not in celery task
    mock_celery.assert_called_once_with(
        [[str(job.id)]],
        queue=QueueNames.JOBS
    )
    assert job.job_status == JOB_STATUS_ERROR
    assert job_2.job_status == JOB_STATUS_IN_PROGRESS


def test_replay_created_notifications(notify_db_session, sample_service, mocker):
    email_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    sms_delivery_queue = mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')

    sms_template = create_template(service=sample_service, template_type='sms')
    email_template = create_template(service=sample_service, template_type='email')
    older_than = (60 * 60) + (60 * 15)  # 1 hour 15 minutes
    # notifications expected to be resent
    old_sms = create_notification(template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                                  status='created')
    old_email = create_notification(template=email_template,
                                    created_at=datetime.utcnow() - timedelta(seconds=older_than),
                                    status='created')
    # notifications that are not to be resent
    create_notification(template=sms_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                        status='sending')
    create_notification(template=email_template, created_at=datetime.utcnow() - timedelta(seconds=older_than),
                        status='delivered')
    create_notification(template=sms_template, created_at=datetime.utcnow(),
                        status='created')
    create_notification(template=email_template, created_at=datetime.utcnow(),
                        status='created')

    replay_created_notifications()
    email_delivery_queue.assert_called_once_with([str(old_email.id)],
                                                 queue='send-email-tasks')
    sms_delivery_queue.assert_called_once_with([str(old_sms.id)],
                                               queue="send-sms-tasks")


def test_replay_created_notifications_get_pdf_for_templated_letter_tasks_for_letters_not_ready_to_send(
        sample_letter_template, mocker
):
    mock_task = mocker.patch('app.celery.scheduled_tasks.get_pdf_for_templated_letter.apply_async')
    create_notification(template=sample_letter_template, billable_units=0,
                        created_at=datetime.utcnow() - timedelta(hours=4))

    create_notification(template=sample_letter_template, billable_units=0,
                        created_at=datetime.utcnow() - timedelta(minutes=20))
    notification_1 = create_notification(template=sample_letter_template, billable_units=0,
                                         created_at=datetime.utcnow() - timedelta(hours=1, minutes=20))
    notification_2 = create_notification(template=sample_letter_template, billable_units=0,
                                         created_at=datetime.utcnow() - timedelta(hours=5))

    replay_created_notifications()

    calls = [call([str(notification_1.id)], queue=QueueNames.CREATE_LETTERS_PDF),
             call([str(notification_2.id)], queue=QueueNames.CREATE_LETTERS_PDF),
             ]
    mock_task.assert_has_calls(calls, any_order=True)


def test_check_job_status_task_does_not_raise_error(sample_template):
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(hours=2),
        scheduled_for=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED)
    create_job(
        template=sample_template,
        notification_count=3,
        created_at=datetime.utcnow() - timedelta(minutes=31),
        processing_started=datetime.utcnow() - timedelta(minutes=31),
        job_status=JOB_STATUS_FINISHED)

    check_job_status()


@freeze_time("2019-05-30 14:00:00")
@pytest.mark.skip(reason="Skipping letter-related functionality for now")
def test_check_if_letters_still_pending_virus_check_restarts_scan_for_stuck_letters(
        mocker,
        sample_letter_template
):
    mock_file_exists = mocker.patch('app.aws.s3.file_exists', return_value=True)
    mock_create_ticket = mocker.spy(NotifySupportTicket, '__init__')
    mock_celery = mocker.patch('app.celery.scheduled_tasks.notify_celery.send_task')

    create_notification(
        template=sample_letter_template,
        status=NOTIFICATION_PENDING_VIRUS_CHECK,
        created_at=datetime.utcnow() - timedelta(seconds=5401),
        reference='one'
    )
    expected_filename = 'NOTIFY.ONE.D.2.C.20190530122959.PDF'

    check_if_letters_still_pending_virus_check()

    mock_file_exists.assert_called_once_with('test-letters-scan', expected_filename)

    mock_celery.assert_called_once_with(
        name=TaskNames.SCAN_FILE,
        kwargs={'filename': expected_filename},
        queue=QueueNames.ANTIVIRUS
    )

    assert mock_create_ticket.called is False


@freeze_time("2019-05-30 14:00:00")
@pytest.mark.skip(reason="Skipping letter-related functionality for now")
def test_check_if_letters_still_pending_virus_check_raises_zendesk_if_files_cant_be_found(
        mocker,
        sample_letter_template
):
    mock_file_exists = mocker.patch('app.aws.s3.file_exists', return_value=False)
    mock_create_ticket = mocker.spy(NotifySupportTicket, '__init__')
    mock_celery = mocker.patch('app.celery.scheduled_tasks.notify_celery.send_task')
    mock_send_ticket_to_zendesk = mocker.patch(
        'app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    create_notification(template=sample_letter_template,
                        status=NOTIFICATION_PENDING_VIRUS_CHECK,
                        created_at=datetime.utcnow() - timedelta(seconds=5400))
    create_notification(template=sample_letter_template,
                        status=NOTIFICATION_DELIVERED,
                        created_at=datetime.utcnow() - timedelta(seconds=6000))
    notification_1 = create_notification(template=sample_letter_template,
                                         status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                         created_at=datetime.utcnow() - timedelta(seconds=5401),
                                         reference='one')
    notification_2 = create_notification(template=sample_letter_template,
                                         status=NOTIFICATION_PENDING_VIRUS_CHECK,
                                         created_at=datetime.utcnow() - timedelta(seconds=70000),
                                         reference='two')

    check_if_letters_still_pending_virus_check()

    assert mock_file_exists.call_count == 2
    mock_file_exists.assert_has_calls([
        call('test-letters-scan', 'NOTIFY.ONE.D.2.C.20190530122959.PDF'),
        call('test-letters-scan', 'NOTIFY.TWO.D.2.C.20190529183320.PDF'),
    ], any_order=True)
    assert mock_celery.called is False

    mock_create_ticket.assert_called_once_with(
        ANY,
        subject='[test] Letters still pending virus check',
        message=ANY,
        ticket_type='incident',
        technical_ticket=True,
        ticket_categories=['notify_letters']
    )
    assert '2 precompiled letters have been pending-virus-check' in mock_create_ticket.call_args.kwargs['message']
    assert f'{(str(notification_1.id), notification_1.reference)}' in mock_create_ticket.call_args.kwargs['message']
    assert f'{(str(notification_2.id), notification_2.reference)}' in mock_create_ticket.call_args.kwargs['message']
    mock_send_ticket_to_zendesk.assert_called_once()


@freeze_time("2019-05-30 14:00:00")
@pytest.mark.skip(reason="Skipping letter-related functionality for now")
def test_check_if_letters_still_in_created_during_bst(mocker, sample_letter_template):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')
    mock_create_ticket = mocker.spy(NotifySupportTicket, '__init__')
    mock_send_ticket_to_zendesk = mocker.patch(
        'app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 1, 12, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 29))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 16, 30))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 29, 17, 29))
    create_notification(template=sample_letter_template, status='delivered', created_at=datetime(2019, 5, 28, 10, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 5, 30, 10, 0))

    check_if_letters_still_in_created()

    message = "2 letters were created before 17.30 yesterday and still have 'created' status. " \
        "Follow runbook to resolve: " \
        "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-Letters-still-in-created."

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_with(
        ANY,
        message=message,
        subject="[test] Letters still in 'created' status",
        ticket_type='incident',
        technical_ticket=True,
        ticket_categories=['notify_letters']
    )
    mock_send_ticket_to_zendesk.assert_called_once()


@freeze_time("2019-01-30 14:00:00")
@pytest.mark.skip(reason="Skipping letter-related functionality for now")
def test_check_if_letters_still_in_created_during_utc(mocker, sample_letter_template):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.error')
    mock_create_ticket = mocker.spy(NotifySupportTicket, '__init__')
    mock_send_ticket_to_zendesk = mocker.patch(
        'app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )

    create_notification(template=sample_letter_template, created_at=datetime(2018, 12, 1, 12, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 29))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 17, 30))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 29, 18, 29))
    create_notification(template=sample_letter_template, status='delivered', created_at=datetime(2019, 1, 29, 10, 0))
    create_notification(template=sample_letter_template, created_at=datetime(2019, 1, 30, 10, 0))

    check_if_letters_still_in_created()

    message = "2 letters were created before 17.30 yesterday and still have 'created' status. " \
        "Follow runbook to resolve: " \
        "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-Letters-still-in-created."

    mock_logger.assert_called_once_with(message)
    mock_create_ticket.assert_called_once_with(
        ANY,
        message=message,
        subject="[test] Letters still in 'created' status",
        ticket_type='incident',
        technical_ticket=True,
        ticket_categories=['notify_letters']
    )
    mock_send_ticket_to_zendesk.assert_called_once()


@pytest.mark.parametrize('offset', (
    timedelta(days=1),
    pytest.param(timedelta(hours=23, minutes=59), marks=pytest.mark.xfail),
    pytest.param(timedelta(minutes=20), marks=pytest.mark.xfail),
    timedelta(minutes=19),
))
def test_check_for_missing_rows_in_completed_jobs_ignores_old_and_new_jobs(
    mocker,
    sample_email_template,
    offset,
):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {"sender_id": None}))
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(
        template=sample_email_template,
        notification_count=5,
        job_status=JOB_STATUS_FINISHED,
        processing_finished=datetime.utcnow() - offset,
    )
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    assert process_row.called is False


def test_check_for_missing_rows_in_completed_jobs(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {"sender_id": None}))
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()

    process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=None
    )


def test_check_for_missing_rows_in_completed_jobs_calls_save_email(mocker, sample_email_template):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {'sender_id': None}))
    save_email_task = mocker.patch('app.celery.tasks.save_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")
    mocker.patch('app.celery.tasks.create_uuid', return_value='uuid')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    save_email_task.assert_called_once_with(
        (
            str(job.service_id),
            "uuid",
            "something_encrypted",
        ),
        {},
        queue="database-tasks"
    )


def test_check_for_missing_rows_in_completed_jobs_uses_sender_id(mocker, sample_email_template, fake_uuid):
    mocker.patch('app.celery.tasks.s3.get_job_and_metadata_from_s3',
                 return_value=(load_example_csv('multiple_email'), {'sender_id': fake_uuid}))
    mock_process_row = mocker.patch('app.celery.scheduled_tasks.process_row')

    job = create_job(template=sample_email_template,
                     notification_count=5,
                     job_status=JOB_STATUS_FINISHED,
                     processing_finished=datetime.utcnow() - timedelta(minutes=20))
    for i in range(0, 4):
        create_notification(job=job, job_row_number=i)

    check_for_missing_rows_in_completed_jobs()
    mock_process_row.assert_called_once_with(
        mock.ANY, mock.ANY, job, job.service, sender_id=fake_uuid
    )


MockServicesSendingToTVNumbers = namedtuple(
    'ServicesSendingToTVNumbers',
    [
        'service_id',
        'notification_count',
    ]
)
MockServicesWithHighFailureRate = namedtuple(
    'ServicesWithHighFailureRate',
    [
        'service_id',
        'permanent_failure_rate',
    ]
)


@pytest.mark.parametrize("failure_rates, sms_to_tv_numbers, expected_message", [
    [
        [MockServicesWithHighFailureRate("123", 0.3)],
        [],
        "1 service(s) have had high permanent-failure rates for sms messages in last "
        "24 hours:\nservice: {}/services/{} failure rate: 0.3,\n".format(
            Test.ADMIN_BASE_URL, "123"
        )
    ],
    [
        [],
        [MockServicesSendingToTVNumbers("123", 300)],
        "1 service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n"
        "service: {}/services/{} count of sms to tv numbers: 300,\n".format(
            Test.ADMIN_BASE_URL, "123"
        )
    ]
])
def test_check_for_services_with_high_failure_rates_or_sending_to_tv_numbers(
    mocker, notify_db_session, failure_rates, sms_to_tv_numbers, expected_message
):
    mock_logger = mocker.patch('app.celery.tasks.current_app.logger.warning')
    mock_create_ticket = mocker.spy(NotifySupportTicket, '__init__')
    mock_send_ticket_to_zendesk = mocker.patch(
        'app.celery.scheduled_tasks.zendesk_client.send_ticket_to_zendesk',
        autospec=True,
    )
    mock_failure_rates = mocker.patch(
        'app.celery.scheduled_tasks.dao_find_services_with_high_failure_rates', return_value=failure_rates
    )
    mock_sms_to_tv_numbers = mocker.patch(
        'app.celery.scheduled_tasks.dao_find_services_sending_to_tv_numbers', return_value=sms_to_tv_numbers
    )

    zendesk_actions = "\nYou can find instructions for this ticket in our manual:\nhttps://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#Deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa

    check_for_services_with_high_failure_rates_or_sending_to_tv_numbers()

    assert mock_failure_rates.called
    assert mock_sms_to_tv_numbers.called
    mock_logger.assert_called_once_with(expected_message)
    mock_create_ticket.assert_called_with(
        ANY,
        message=expected_message + zendesk_actions,
        subject="[test] High failure rates for sms spotted for services",
        ticket_type='incident',
        technical_ticket=True
    )
    mock_send_ticket_to_zendesk.assert_called_once()
