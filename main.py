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
  
  # get sub-value from the JWT
  # reference: https://developers.google.com/identity/sign-in/web/backend-auth
  idinfo = id_token.verify_oauth2_token(JWT, google.auth.transport.requests.Request(), CLIENT_ID)
  userid = idinfo['sub']

  # query datastore for all users
  query = client.query(kind=constants.users)
  results = list(query.fetch())

  # check if user with the sub-value already exists
  user_exists = False
  for user in results:
    if user['id'] == userid:
      user_exists = True
      break
  
  # if user does not exist, add user to the datastore with boats initialized empty
  if not user_exists:
    new_user = datastore.entity.Entity(key=client.key(constants.users))
    new_user.update({"id": userid, "boats": []})
    client.put(new_user)
  
	# render oauth page with the received JWT value 
  return render_template("oauth.html", JWT_value=JWT)

# get route for /users
@app.route('/users', methods=['GET'])
def get_users():
  if request.method == 'GET':
    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    query = client.query(kind=constants.users)
    results = list(query.fetch())
    return (jsonify(results), 200)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)