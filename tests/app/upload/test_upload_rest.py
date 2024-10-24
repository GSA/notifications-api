from datetime import datetime
from unittest.mock import MagicMock

from app.upload.rest import get_paginated_uploads


# TODO
def test_get_paginated_uploads(mocker):
    mock_current_app = mocker.patch("app.upload.rest.current_app")
    mock_dao_get_uploads = mocker.patch("app.upload.rest.dao_get_uploads_by_service_id")
    mock_pagination_links = mocker.patch("app.upload.rest.pagination_links")
    mock_fetch_notification_statuses = mocker.patch(
        "app.upload.rest.fetch_notification_statuses_for_job"
    )
    mock_midnight_n_days_ago = mocker.patch("app.upload.rest.midnight_n_days_ago")
    mock_dao_get_notification_outcomes = mocker.patch(
        "app.upload.rest.dao_get_notification_outcomes_for_job"
    )

    mock_current_app.config = {"PAGE_SIZE": 10}
    mock_pagination = MagicMock()
    mock_pagination.items = [
        MagicMock(
            id="upload_1",
            original_file_name="file1.csv",
            notification_count=100,
            scheduled_for=None,
            created_at=datetime(2024, 10, 1, 12, 0, 0),
            upload_type="job",
            template_type="sms",
            recipient="recipient@example.com",
            processing_started=datetime(2024, 10, 2, 12, 0, 0),
        ),
        MagicMock(
            id="upload_2",
            original_file_name="file2.csv",
            notification_count=50,
            scheduled_for=datetime(2024, 10, 3, 12, 0, 0),
            created_at=None,
            upload_type="letter",
            template_type="letter",
            recipient="recipient2@example.com",
            processing_started=None,
        ),
    ]
    mock_pagination.per_page = 10
    mock_pagination.total = 2
    mock_dao_get_uploads.return_value = mock_pagination
    mock_midnight_n_days_ago.return_value = datetime(2024, 9, 30, 0, 0, 0)
    mock_fetch_notification_statuses.return_value = [
        MagicMock(status="delivered", count=90),
        MagicMock(status="failed", count=10),
    ]
    mock_dao_get_notification_outcomes.return_value = [
        MagicMock(status="pending", count=40),
        MagicMock(status="delivered", count=60),
    ]
    mock_pagination_links.return_value = {"self": "/uploads?page=1"}
    # result =
    get_paginated_uploads("service_id_123", limit_days=7, page=1)
    mock_dao_get_uploads.assert_called_once_with(
        "service_id_123", limit_days=7, page=1, page_size=10
    )
    mock_midnight_n_days_ago.assert_called_once_with(3)
    # mock_fetch_notification_statuses.assert_called_once_with("upload_1")
    mock_dao_get_notification_outcomes.assert_called_once_with(
        "service_id_123", "upload_1"
    )
    mock_pagination_links.assert_called_once_with(
        mock_pagination, ".get_uploads_by_service", service_id="service_id_123"
    )

    # expected_data = {
    #     "data": [
    #         {
    #             "id": "upload_1",
    #             "original_file_name": "file1.csv",
    #             "notification_count": 100,
    #             "created_at": "2024-10-01 12:00:00",
    #             "upload_type": "job",
    #             "template_type": "sms",
    #             "recipient": "recipient@example.com",
    #             "statistics": [
    #                 {"status": "delivered", "count": 90},
    #                 {"status": "failed", "count": 10},
    #             ],
    #         },
    #         {
    #             "id": "upload_2",
    #             "original_file_name": "file2.csv",
    #             "notification_count": 50,
    #             "created_at": "2024-10-03 12:00:00",
    #             "upload_type": "letter",
    #             "template_type": "letter",
    #             "recipient": "recipient2@example.com",
    #             "statistics": [],
    #         },
    #     ],
    #     "page_size": 10,
    #     "total": 2,
    #     "links": {"self": "/uploads?page=1"},
    # }
    # assert result == expected_data
