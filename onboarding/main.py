"""main.py — Flask app factory and entry point"""
import os
from flask import Flask
from config import Config
from db import db
from routes import blueprints
from api import api_blueprints


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.config.from_object(Config)

    # Init database
    os.makedirs(os.path.join(os.path.dirname(__file__), "data"), exist_ok=True)
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Register route blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    # Register API blueprints
    for bp in api_blueprints:
        app.register_blueprint(bp)

    return app


app = create_app()

if __name__ == "__main__":
    print(f"\n  ZivoPay Service Center  →  http://localhost:{Config.PORT}\n")
    app.run(debug=Config.DEBUG, host="0.0.0.0", port=Config.PORT)
