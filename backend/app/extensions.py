"""Flask extension instances.

They are created here **unbound** and attached to the app inside
``create_app`` so that modules can import them without importing the app
(avoids circular imports and keeps module boundaries clean).
"""

from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
