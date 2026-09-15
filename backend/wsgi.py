"""WSGI entrypoint.

Run locally with ``flask --app wsgi run`` or serve with gunicorn:
``gunicorn wsgi:app``.
"""

from app import create_app

app = create_app()
