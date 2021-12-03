from google.cloud import datastore
from flask import Flask, request, jsonify, render_template
import flask
import requests
import json
import constants
from google.oauth2 import id_token
import google.auth.transport
import yaml
import uuid

# instantiate flask app and datastore client
app = Flask(__name__)
client = datastore.Client()

# global variables for Google OAuth 2.0
credentials = yaml.safe_load(open('credentials.yaml'))
AUTH_URI = credentials['auth_uri']
CLIENT_ID = credentials['client_id']
CLIENT_SECRET = credentials['client_secret']
REDIRECT_URI = credentials['redirect_uri']
RESPONSE_TYPE = "code"
SCOPE = "profile"
STATE = 0

# index route
@app.route('/')
def index():
  # generate a random state value
  # reference: https://stackoverflow.com/questions/2511222/efficiently-generate-a-16-character-alphanumeric-string
  global STATE
  STATE = uuid.uuid4().hex

  # request_url for client to access end-user resources on the server
  request_url = AUTH_URI + "?response_type=" + RESPONSE_TYPE + "&client_id=" + CLIENT_ID + "&redirect_uri=" + REDIRECT_URI + "&scope=" + SCOPE + "&state=" + STATE
  return render_template("index.html", request=request_url)

# oauth route
# reference: https://developers.google.com/identity/protocols/oauth2/web-server#httprest
@app.route('/oauth')
def oauth():
  # client sends access code and client secret to server
	auth_code = flask.request.args.get('code') 
	data = {
    'code': auth_code,
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'redirect_uri': REDIRECT_URI,
    'grant_type': 'authorization_code'
  }
	r = requests.post('https://www.googleapis.com/oauth2/v4/token', data=data)

	# get JWT from the server
	JWT = r.json()["id_token"]

	# render oauth page with the received JWT value 
	return render_template("oauth.html", JWT_value=JWT)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)