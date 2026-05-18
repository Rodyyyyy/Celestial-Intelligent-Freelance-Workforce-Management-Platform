from flask_socketio import emit, join_room
from flask import request, session

def register_socket_handlers(socketio):

    @socketio.on('connect')
    def handle_connect():
        user_id = session.get('user_id')
        role = session.get('role')
        
        if user_id:
            join_room(f'user_{user_id}')
            emit('connected', {
                'status': 'success',
                'user_id': user_id,
                'message': 'Real-time connection established'
            })
        
        if role:
            join_room(f'role_{role}')

    @socketio.on('disconnect')
    def handle_disconnect():
        pass

    # Allow frontend to manually join rooms if needed
    @socketio.on('join')
    def on_join(data):
        room = data.get('room')
        if room:
            join_room(room)
            emit('joined', {'room': room})