import os
from database import init_db
from auth import ensure_passcode
from network import start_reticulum
import routes # register routes
from app import app
import network

def initialize_app():
    # Prevent initialization in the Flask reloader's master process
    # to avoid TCP port conflicts with Reticulum.
    if os.environ.get("FLASK_RUN_FROM_CLI") == "1" and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    # Prevent double initialization
    if network.destination is not None:
        return
    
    init_db()
    ensure_passcode()
    start_reticulum()

initialize_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
