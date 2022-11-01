from app.config import QueueNames


def test_queue_names_all_queues_correct():
    # Need to ensure that all_queues() only returns queue names used in API
    queues = QueueNames.all_queues()
    assert len(queues) == 17
    assert set([
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
    ]) == set(queues)
