from google.cloud import datastore
from flask import Flask, request, jsonify
import json
import constants

# instantiate flask app and datastore client
app = Flask(__name__)
client = datastore.Client()

# index route
@app.route('/')
def index():
  return "Please navigate to /boats or /loads to use this API"

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)