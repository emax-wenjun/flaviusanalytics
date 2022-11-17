import os

from flask import Flask
from flask import request
from flask import render_template
from flaviusanalytics.results import race_list, fetch_and_update
from flaviusanalytics.polls import fetch_and_update_polls
from flaviusanalytics.utils import send_text
from datetime import datetime

import threading, atexit

def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaviusanalytics.sqlite'),
    )

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass
        
    from . import db
    db.init_app(app)

    from . import results
    app.register_blueprint(results.bp)

    from . import overview
    app.register_blueprint(overview.overview_bp)
    
    def fetch_timer():
        fetch_and_update()
        newthread = threading.Timer(10, fetch_timer)
        newthread.start()
    
    def fetch_polls_timer():
        fetch_and_update_polls()
        newthread = threading.Timer(300, fetch_polls_timer)
        newthread.start()

    # Initiate
    if "DYNO" in os.environ:
        send_text("Booting on Heroku!")
    thread = threading.Thread(target=fetch_timer, daemon=True)
    thread.start()
    #thread_polls = threading.Thread(target=fetch_polls_timer, daemon=True)
    #thread_polls.start()
    return app