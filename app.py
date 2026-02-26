from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "APP FUNCIONANDO"

@app.route("/dashboard")
def dashboard():
    return "DASHBOARD OK"