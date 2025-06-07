from flask import Flask
import logging

# Set up basic configuration
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')


def create_app():
    app = Flask(__name__)
    
    # Register blueprints or routes
    from .views import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    return app