from functools import wraps
from flask import request, jsonify


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Stub: in production, validate a JWT or session token here.
        # For local development, all requests are treated as authenticated.
        return f(*args, **kwargs)
    return decorated
