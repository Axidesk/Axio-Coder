from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

app = Flask(__name__, static_folder=None, template_folder=None)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
