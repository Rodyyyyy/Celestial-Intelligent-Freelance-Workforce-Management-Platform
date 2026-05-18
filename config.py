"""config.py — Application configuration."""
import os, secrets


class Config:
    SECRET_KEY          = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    DATABASE            = os.environ.get('DATABASE', 'celestial.db')
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE   = False   # set True behind HTTPS
    PERMANENT_SESSION_LIFETIME = 86400  # 24 h


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
