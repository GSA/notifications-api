from flask import Blueprint
from app import socketio

test_bp = Blueprint('test', __name__)

@test_bp.route('/test-emit', methods=["GET"])
def test_emit():
    socketio.emit('job_update', {
        'job_id': 'abc123',
        'status': 'Test message from API'
    })
    return "Event emitted!"
