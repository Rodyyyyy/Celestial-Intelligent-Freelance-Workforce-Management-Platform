# utils/__init__.py
import re
import math
from flask import jsonify

def ok(data=None, message='Success', **kwargs):
    payload = {'success': True, 'message': message}
    if data is not None:
        payload['data'] = data
    payload.update(kwargs)
    return jsonify(payload), 200

def created(data=None, message='Created'):
    payload = {'success': True, 'message': message}
    if data is not None:
        payload['data'] = data
    return jsonify(payload), 201

def err(message='Error', code=400, **kwargs):
    payload = {'success': False, 'error': message, 'code': code}
    payload.update(kwargs)
    return jsonify(payload), code

def not_found(message='Not found'):
    return err(message, 404)

def forbidden(message='Forbidden'):
    return err(message, 403)

def paginate(items: list, page: int, per_page: int = 20) -> dict:
    total = len(items)
    start = (page - 1) * per_page
    end   = start + per_page
    return {
        'items':      items[start:end],
        'total':      total,
        'page':       page,
        'per_page':   per_page,
        'pages':      max(1, math.ceil(total / per_page))
    }

def validate_email(email: str) -> bool:
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email or ''))

def clean_skills(skills_str: str) -> str:
    """Normalise comma-separated skills: strip whitespace, title-case."""
    parts = [s.strip().title() for s in (skills_str or '').split(',') if s.strip()]
    return ', '.join(parts)