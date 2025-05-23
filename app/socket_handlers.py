from flask import current_app, request
from flask_socketio import join_room, leave_room


def register_socket_handlers(socketio):
    @socketio.on("connect")
    def on_connect():
        current_app.logger.info(
            f"Socket {request.sid} connected from {request.environ.get('HTTP_ORIGIN')}"
        )
        return True

    @socketio.on("disconnect")
    def on_disconnect():
        current_app.logger.info(f"Socket {request.sid} disconnected")

    @socketio.on("join")
    def on_join(data):  # noqa: F401
        room = data.get("room")
        join_room(room)
        current_app.logger.info(f"Socket {request.sid} joined room {room}")

    @socketio.on("leave")
    def on_leave(data):  # noqa: F401
        room = data.get("room")
        leave_room(room)
        current_app.logger.info(f"Socket {request.sid} left room {room}")
