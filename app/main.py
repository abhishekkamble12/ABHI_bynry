"""
StockFlow Flask application entry point.

db is defined at module level so app/models.py can import it without
creating a circular dependency. The create_app() factory pattern keeps
the application testable and configurable.
"""

import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

# db is defined here at module level so models.py can import it directly
# without triggering a circular import
db = SQLAlchemy()


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Read DATABASE_URL from environment; fall back to a local default
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "postgresql://localhost/stockflow"
    )
    # Disable modification tracking — not needed and adds overhead
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Bind the SQLAlchemy instance to this app
    db.init_app(app)

    # Register the routes blueprint (imported here to avoid circular imports)
    from app.routes import bp
    app.register_blueprint(bp)

    return app


# Module-level app instance so `flask run` works without extra config
app = create_app()
