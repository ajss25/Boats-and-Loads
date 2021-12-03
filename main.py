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
  
  # if user does not exist, add user to the datastore
  if not user_exists:
    new_user = datastore.entity.Entity(key=client.key(constants.users))
    new_user.update({"id": userid})
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

# post route for /boats
@app.route('/boats', methods=['POST', 'GET'])
def post_boats():
  if request.method == 'POST':
    content = request.get_json()

    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
		# reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the request is missing any of the required attributes, return 400
    if "name" not in content or "type" not in content or "length" not in content:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)
  
    new_boat = datastore.entity.Entity(key=client.key(constants.boats))
    new_boat.update({
      "name": content["name"],
      "type": content["type"],
      "length": content["length"],
      "owner": userid,
      "loads": []
    })
    client.put(new_boat)

    self_url = request.base_url + "/" + str(new_boat.key.id)
    new_boat["id"] = new_boat.key.id
    new_boat["self"] = self_url
    return (jsonify(new_boat), 201)

  elif request.method == 'GET':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
		# reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # get all boats with pagination
    query = client.query(kind=constants.boats)
    q_limit = int(request.args.get('limit', '5'))
    q_offset = int(request.args.get('offset', '0'))
    l_iterator = query.fetch(limit=q_limit, offset=q_offset)
    pages = l_iterator.pages
    results = list(next(pages))

    if l_iterator.next_page_token:
      next_offset = q_offset + q_limit
      next_url = request.base_url + "?limit=" + str(q_limit) + "&offset=" + str(next_offset)
    else:
      next_url = None

    user_boats = []

    for boat in results:
      if boat["owner"] == userid:
        boat["id"] = boat.key.id
        user_boats.append(boat)
    
    response = {"boats": user_boats}

    # add total number of boats for user in response
    response["total"] = len(user_boats)

    # add next url if more than five boats for user
    if next_url:
      response["next"] = next_url

    # return response and 200
    return (jsonify(response), 200)

# get, patch, put, and delete routes for /boats/boat_id
@app.route('/boats/<boat_id>', methods=['GET', 'PATCH', 'PUT', 'DELETE'])
def get_patch_put_delete_boat(boat_id):
  boat_key = client.key(constants.boats, int(boat_id))
  boat = client.get(key=boat_key)

  if request.method == 'GET':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    # reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the boat does not exist, return 404
    if not boat:
      return (jsonify({"Error": "No boat with this boat_id exists"}), 404)

    # if the boat does not belong to the user making the request, return 403
    if boat["owner"] != userid:
      return (jsonify({"Error": "The user making the request does not have access to this resource"}), 403)

    boat["self"] = request.base_url
    boat["id"] = boat_id
    return (jsonify(boat), 200)
  
  if request.method == 'PATCH':
    content = request.get_json()

    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    # reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the boat does not exist, return 404
    if not boat:
      return (jsonify({"Error": "No boat with this boat_id exists"}), 404)

    # if the boat does not belong to the user making the request, return 403
    if boat["owner"] != userid:
      return (jsonify({"Error": "The user making the request does not have access to this resource"}), 403)

    # if the request does not provide exactly one or two attributes to edit, return 400
    if len(content) != 1 and len(content) != 2:
      return (jsonify({"Error": "The request object did not provide a subset of the required attributes"}), 400)

    # patch the boat and return 200
    if "name" in content:
      boat.update({"name": content["name"]})
    if "type" in content:
      boat.update({"type": content["type"]})
    if "length" in content:
      boat.update({"length": content["length"]})
    client.put(boat)

    boat["self"] = request.base_url
    boat["id"] = boat_id
    return (jsonify(boat), 200)
  
  elif request.method == 'PUT':
    content = request.get_json()

    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    # reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the boat does not exist, return 404
    if not boat:
      return (jsonify({"Error": "No boat with this boat_id exists"}), 404)

    # if the boat does not belong to the user making the request, return 403
    if boat["owner"] != userid:
      return (jsonify({"Error": "The user making the request does not have access to this resource"}), 403)

    # if the request does not provide exactly three attributes to edit, return 400
    if len(content) != 3:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)

    # put the boat and return 200
    boat.update({"name": content["name"]})
    boat.update({"type": content["type"]})
    boat.update({"length": content["length"]})
    client.put(boat)

    boat["self"] = request.base_url
    boat["id"] = boat_id
    return (jsonify(boat), 200)

  elif request.method == 'DELETE':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    # reference: https://stackoverflow.com/questions/63518441/how-to-read-a-bearer-token-from-postman-into-python-code
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    # reference: https://developers.google.com/identity/sign-in/web/backend-auth
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the boat does not exist, return 404
    if not boat:
      return (jsonify({"Error": "No boat with this boat_id exists"}), 404)

    # if the boat does not belong to the user making the request, return 403
    if boat["owner"] != userid:
      return (jsonify({"Error": "The user making the request does not have access to this resource"}), 403)

    # remove boat from load entities before deleting the boat
    if not boat["loads"]:
      client.delete(boat)
    else:
      for loaded in boat["loads"]:
        load_key = client.key(constants.loads, int(loaded["id"]))
        load = client.get(key=load_key)
        load["carrier"] = None
        client.put(load)
      client.delete(boat)
    return('', 204)

# post route for /loads
@app.route('/loads', methods=['POST'])
def post_loads():
  if request.method == 'POST':
    content = request.get_json()
    
    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the request is missing any of the required attributes, return 400
    if "volume" not in content or "content" not in content or "creation_date" not in content:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)
  
    new_load = datastore.entity.Entity(key=client.key(constants.loads))
    new_load.update({
      "volume": content["volume"],
      "content": content["content"],
      "creation_date": content["creation_date"],
      "carrier": None
    })
    client.put(new_load)

    self_url = request.base_url + "/" + str(new_load.key.id)
    new_load["id"] = new_load.key.id
    new_load["self"] = self_url
    return (jsonify(new_load), 201)

# get route for /loads/load_id
@app.route('/loads/<load_id>', methods=['GET', 'PATCH', 'PUT', 'DELETE'])
def get_load(load_id):
  load_key = client.key(constants.loads, int(load_id))
  load = client.get(key=load_key)

  if request.method == 'GET':
    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # return load and 200
    load["self"] = request.base_url
    load["id"] = load_id
    return (jsonify(load), 200)

  if request.method == 'PATCH':
    content = request.get_json()

    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # if the request does not provide exactly one or two attributes to edit, return 400
    if len(content) != 1 and len(content) != 2:
      return (jsonify({"Error": "The request object did not provide a subset of the required attributes"}), 400)

    # patch the load and return 200
    if "volume" in content:
      load.update({"volume": content["volume"]})
    if "content" in content:
      load.update({"content": content["content"]})
    if "creation_date" in content:
      load.update({"creation_date": content["creation_date"]})
    client.put(load)

    load["self"] = request.base_url
    load["id"] = load_id
    return (jsonify(load), 200)

  elif request.method == 'PUT':
    content = request.get_json()

    # if the request contains accept header besides application/json, or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # if the request does not provide exactly three attributes to edit, return 400
    if len(content) != 3:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)

    # put the load and return 200
    load.update({"volume": content["volume"]})
    load.update({"content": content["content"]})
    load.update({"creation_date": content["creation_date"]})
    client.put(load)

    load["self"] = request.base_url
    load["id"] = load_id
    return (jsonify(load), 200)
  
  elif request.method == 'DELETE':
    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # update boat with the load before deleting load
    if not load["carrier"]:
      client.delete(load)
    else:
      boat_key = client.key(constants.boats, int(load["carrier"]["id"]))
      boat = client.get(key=boat_key)
      for loaded in boat["loads"]:
        if loaded["id"] == str(load.key.id):
          boat["loads"].remove(loaded)
          client.put(boat)
          break
      client.delete(load)
    return('', 204)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)