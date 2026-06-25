from .config import Config


def create_app(config_class=Config):
    from flask import Flask
    from .db import init_db
    from .routes import bp

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)
    init_db(app.config["DATABASE_URL"])
    app.register_blueprint(bp)
    return app
