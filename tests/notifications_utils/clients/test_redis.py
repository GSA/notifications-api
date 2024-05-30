from notifications_utils.clients.redis import rate_limit_cache_key


def test_rate_limit_cache_key(sample_service):
    assert rate_limit_cache_key(sample_service.id, "TEST") == "{}-TEST".format(
        sample_service.id
    )
