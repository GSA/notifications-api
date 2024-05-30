from notifications_utils import request_helper


def test_request_id_is_set_on_response(app):
    request_helper.init_app(app)
    client = app.test_client()

    with app.app_context():
        response = client.get(
            "/", headers={"X-B3-TraceId": "generated", "X-B3-SpanId": "generated"}
        )
        assert response.headers["X-B3-TraceId"] == "generated"
        assert response.headers["X-B3-SpanId"] == "generated"


def test_request_id_is_set_on_error_response(app):
    request_helper.init_app(app)
    client = app.test_client()
    # turn off DEBUG so that the flask default error handler gets triggered
    app.config["DEBUG"] = False

    @app.route("/")
    def error_route():
        raise Exception()

    with app.app_context():
        response = client.get(
            "/", headers={"X-B3-TraceId": "generated", "X-B3-SpanId": "generated"}
        )
        assert response.status_code == 500
        assert response.headers["X-B3-TraceId"] == "generated"
        assert response.headers["X-B3-SpanId"] == "generated"
