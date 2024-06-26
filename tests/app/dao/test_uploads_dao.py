from datetime import timedelta

from freezegun import freeze_time

from app.dao.uploads_dao import dao_get_uploads_by_service_id
from app.enums import JobStatus, NotificationStatus, NotificationType, TemplateType
from app.utils import utc_now
from tests.app.db import (
    create_job,
    create_notification,
    create_service,
    create_service_data_retention,
    create_template,
)


def create_uploaded_letter(
    letter_template,
    service,
    status=NotificationStatus.CREATED,
    created_at=None,
):
    return create_notification(
        template=letter_template,
        to_field="file-name",
        status=status,
        reference="dvla-reference",
        client_reference="file-name",
        one_off=True,
        created_by_id=service.users[0].id,
        created_at=created_at,
    )


def create_uploaded_template(service):
    return create_template(
        service,
        template_type=TemplateType.LETTER,
        template_name="Pre-compiled PDF",
        subject="Pre-compiled PDF",
        content="",
        hidden=True,
    )


@freeze_time("2020-02-02 09:00")  # GMT time
def test_get_uploads_for_service(sample_template):
    create_service_data_retention(
        sample_template.service, NotificationType.SMS, days_of_retention=9
    )
    job = create_job(sample_template, processing_started=utc_now())

    other_service = create_service(service_name="other service")
    other_template = create_template(service=other_service)
    other_job = create_job(other_template, processing_started=utc_now())

    uploads_from_db = dao_get_uploads_by_service_id(job.service_id).items
    other_uploads_from_db = dao_get_uploads_by_service_id(other_job.service_id).items

    assert len(uploads_from_db) == 1

    assert uploads_from_db[0] == (
        job.id,
        job.original_file_name,
        job.notification_count,
        TemplateType.SMS,
        9,
        job.created_at,
        job.scheduled_for,
        job.processing_started,
        job.job_status,
        "job",
        None,
    )

    assert len(other_uploads_from_db) == 1
    assert other_uploads_from_db[0] == (
        other_job.id,
        other_job.original_file_name,
        other_job.notification_count,
        other_job.template.template_type,
        7,
        other_job.created_at,
        other_job.scheduled_for,
        other_job.processing_started,
        other_job.job_status,
        "job",
        None,
    )

    assert uploads_from_db[0] != other_uploads_from_db[0]


def test_get_uploads_orders_by_processing_started_desc(sample_template):
    days_ago = utc_now() - timedelta(days=3)
    upload_1 = create_job(
        sample_template,
        processing_started=utc_now() - timedelta(days=1),
        created_at=days_ago,
        job_status=JobStatus.IN_PROGRESS,
    )
    upload_2 = create_job(
        sample_template,
        processing_started=utc_now() - timedelta(days=2),
        created_at=days_ago,
        job_status=JobStatus.IN_PROGRESS,
    )

    results = dao_get_uploads_by_service_id(service_id=sample_template.service_id).items

    assert len(results) == 2
    assert results[0].id == upload_1.id
    assert results[1].id == upload_2.id


def test_get_uploads_returns_empty_list(sample_service):
    items = dao_get_uploads_by_service_id(sample_service.id).items
    assert items == []
