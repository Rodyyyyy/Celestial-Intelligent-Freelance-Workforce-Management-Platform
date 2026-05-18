from flask import current_app

def emit_realtime(event, data, user_id=None, role=None, broadcast=False):
    """Enhanced real-time emitter"""
    socketio = current_app.extensions.get('socketio')
    if not socketio:
        print(f"[SocketIO] Not available for event: {event}")
        return

    try:
        if broadcast:
            socketio.emit(event, data, broadcast=True, namespace='/')
        elif user_id:
            socketio.emit(event, data, room=f'user_{user_id}', namespace='/')
        elif role:
            socketio.emit(event, data, room=f'role_{role}', namespace='/')
        else:
            socketio.emit(event, data, broadcast=True, namespace='/')
    except Exception as e:
        print(f"[SocketIO Error] {e}")