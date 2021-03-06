from google.cloud import datastore
from google.oauth2 import id_token
import google.auth.transport
import flask
from flask import Flask, request, jsonify, render_template
import requests
import constants
import uuid
import yaml

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

  # request url for client to access end-user resources on the server
  request_url = AUTH_URI + "?response_type=" + RESPONSE_TYPE + "&client_id=" + CLIENT_ID + "&redirect_uri=" + REDIRECT_URI + "&scope=" + SCOPE + "&state=" + STATE
  return render_template("index.html", request=request_url)

# oauth route
# reference: https://developers.google.com/identity/protocols/oauth2/web-server#httprest
@app.route('/oauth')
def oauth():
  # client sends access code and client secret to the server
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
  
  # get the 'sub' value from the JWT
  # reference: https://developers.google.com/identity/sign-in/web/backend-auth
  idinfo = id_token.verify_oauth2_token(JWT, google.auth.transport.requests.Request(), CLIENT_ID)
  userid = idinfo['sub']

  # query datastore for all existing users
  query = client.query(kind=constants.users)
  results = list(query.fetch())

  # check if a user with the 'sub' value id already exists
  user_exists = False
  for user in results:
    if user['id'] == userid:
      user_exists = True
      break
  
  # if user does not exist, add the new user to datastore
  if not user_exists:
    new_user = datastore.entity.Entity(key=client.key(constants.users))
    new_user.update({"id": userid})
    client.put(new_user)
  
	# render oauth page with the received JWT value and user's unique id
  return render_template("oauth.html", JWT_value=JWT, id_value=userid)

# get route for /users
@app.route('/users', methods=['GET'])
def get_users():
  if request.method == 'GET':
    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # query all users in datastore and return results
    query = client.query(kind=constants.users)
    results = list(query.fetch())
    return (jsonify(results), 200)

# post and get routes for /boats
@app.route('/boats', methods=['POST', 'GET'])
def post_boats():
  # add a new boat
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
    
    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the request is missing any of the required attributes, return 400
    if "name" not in content or "type" not in content or "length" not in content:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)

    # add the boat to datastore
    new_boat = datastore.entity.Entity(key=client.key(constants.boats))
    new_boat.update({
      "name": content["name"],
      "type": content["type"],
      "length": content["length"],
      "owner": userid,
      "loads": []
    })
    client.put(new_boat)

    # return representation of new boat
    self_url = request.base_url + "/" + str(new_boat.key.id)
    new_boat["id"] = new_boat.key.id
    new_boat["self"] = self_url
    return (jsonify(new_boat), 201)

  # get all boats
  elif request.method == 'GET':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # get all boats with pagination
    query = client.query(kind=constants.boats)
    total = len(list(query.fetch()))
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

    # filter boats that belong to the user with the request
    user_boats = []
    for boat in results:
      if boat["owner"] == userid:
        boat["id"] = boat.key.id
        boat["self"] = request.base_url + "/" + str(boat.key.id)
        user_boats.append(boat)
    
    # create response with user's boats
    response = {"boats": user_boats}

    # add total number of boats for user in response
    response["total"] = total

    # add next url if more than five boats for user
    if next_url:
      response["next"] = next_url

    # return the response
    return (jsonify(response), 200)

# get, patch, put, and delete routes for /boats/boat_id
@app.route('/boats/<boat_id>', methods=['GET', 'PATCH', 'PUT', 'DELETE'])
def get_patch_put_delete_boat(boat_id):
  boat_key = client.key(constants.boats, int(boat_id))
  boat = client.get(key=boat_key)

  # get a boat
  if request.method == 'GET':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides 'application/json' or is missing accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the boat does not exist, return 404
    if not boat:
      return (jsonify({"Error": "No boat with this boat_id exists"}), 404)

    # if the boat does not belong to the user making the request, return 403
    if boat["owner"] != userid:
      return (jsonify({"Error": "The user making the request does not have access to this resource"}), 403)

    # add id and self representation for loads on the boat, if any
    for loaded in boat["loads"]:
      loaded["self"] = request.url_root + "loads/" + loaded["id"]
      loaded["id"] = int(loaded["id"])

    # add id and self representation of the boat and return response
    boat["self"] = request.base_url
    boat["id"] = int(boat_id)
    return (jsonify(boat), 200)
  
  # patch a boat
  elif request.method == 'PATCH':
    content = request.get_json()

    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides 'application/json' or is missing accept header, return 406
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

    # update the boat
    if "name" in content:
      boat.update({"name": content["name"]})
    if "type" in content:
      boat.update({"type": content["type"]})
    if "length" in content:
      boat.update({"length": content["length"]})
    client.put(boat)

    # add id and self representation of the boat and return response
    boat["self"] = request.base_url
    boat["id"] = int(boat_id)
    return (jsonify(boat), 200)
  
  # put a boat
  elif request.method == 'PUT':
    content = request.get_json()

    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
    try:
      idinfo = id_token.verify_oauth2_token(request_JWT, google.auth.transport.requests.Request(), CLIENT_ID)
      userid = idinfo['sub']
    except ValueError:
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)

    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
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

    # update the boat
    boat.update({"name": content["name"]})
    boat.update({"type": content["type"]})
    boat.update({"length": content["length"]})
    client.put(boat)

    # add id and self representation of the boat and return response
    boat["self"] = request.base_url
    boat["id"] = int(boat_id)
    return (jsonify(boat), 200)

  # delete a boat
  elif request.method == 'DELETE':
    # if the request is missing a JWT, return 401
    if not request.headers.get('Authorization'):
      return (jsonify({"Error": "The request object is missing a JWT or contains invalid JWT"}), 401)
    
    # get the JWT from the request
    request_JWT = request.headers.get('Authorization').split()[1]

    # if the JWT is invalid, return 401
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

    # remove boat, if necessary, from load/s as carriers before deleting the boat, and return response
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

# post and get routes for /loads
@app.route('/loads', methods=['POST', 'GET'])
def post_get_loads():
  # add a new load
  if request.method == 'POST':
    content = request.get_json()
    
    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the request is missing any of the required attributes, return 400
    if "volume" not in content or "content" not in content or "creation_date" not in content:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)

    # add the new load to datastore
    new_load = datastore.entity.Entity(key=client.key(constants.loads))
    new_load.update({
      "volume": content["volume"],
      "content": content["content"],
      "creation_date": content["creation_date"],
      "carrier": None
    })
    client.put(new_load)

    # add id and self representation of the load and return response
    self_url = request.base_url + "/" + str(new_load.key.id)
    new_load["id"] = new_load.key.id
    new_load["self"] = self_url
    return (jsonify(new_load), 201)
  
  # get all loads
  elif request.method == 'GET':
    # if the request contains accept header besides 'application/json', or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # get all loads with pagination
    query = client.query(kind=constants.loads)
    total = len(list(query.fetch()))
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

    # add id and self representation for each load
    for load in results:
      load["id"] = load.key.id
      load["self"] = request.base_url + "/" + str(load.key.id)

    # create response
    response = {"loads": results}

    # add total number of loads in response
    response["total"] = total

    # add next url if more than five loads
    if next_url:
      response["next"] = next_url

    # return response
    return (jsonify(response), 200)

# get, patch, put, and delete routes for /loads/load_id
@app.route('/loads/<load_id>', methods=['GET', 'PATCH', 'PUT', 'DELETE'])
def get_load(load_id):
  load_key = client.key(constants.loads, int(load_id))
  load = client.get(key=load_key)

  # get a load
  if request.method == 'GET':
    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # if the load is on a boat, add id and self representation for the boat
    if load["carrier"]:
      load["carrier"]["self"] = request.url_root + "boats/" + load["carrier"]["id"]
      load["carrier"]["id"] = int(load["carrier"]["id"])

    # add id and self representation  of the load and return response
    load["self"] = request.base_url
    load["id"] = int(load_id)
    return (jsonify(load), 200)

  # patch a load
  elif request.method == 'PATCH':
    content = request.get_json()

    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # if the request does not provide exactly one or two attributes to edit, return 400
    if len(content) != 1 and len(content) != 2:
      return (jsonify({"Error": "The request object did not provide a subset of the required attributes"}), 400)

    # update the load
    if "volume" in content:
      load.update({"volume": content["volume"]})
    if "content" in content:
      load.update({"content": content["content"]})
    if "creation_date" in content:
      load.update({"creation_date": content["creation_date"]})
    client.put(load)

    # add id and self representation of the load and return response
    load["self"] = request.base_url
    load["id"] = int(load_id)
    return (jsonify(load), 200)

  # put a load
  elif request.method == 'PUT':
    content = request.get_json()

    # if the request contains accept header besides 'application/json' or is missing the accept header, return 406
    if 'application/json' not in request.accept_mimetypes:
      return (jsonify({"Error": "MIME type not supported by the endpoint or the Accept header is missing"}), 406)

    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # if the request does not provide exactly three attributes to edit, return 400
    if len(content) != 3:
      return (jsonify({"Error": "The request object is missing at least one of the required attributes"}), 400)

    # update the load
    load.update({"volume": content["volume"]})
    load.update({"content": content["content"]})
    load.update({"creation_date": content["creation_date"]})
    client.put(load)

    # add id and self representation of the load and return response
    load["self"] = request.base_url
    load["id"] = int(load_id)
    return (jsonify(load), 200)
  
  # delete a load
  elif request.method == 'DELETE':
    # if the load does not exist, return 404
    if not load:
      return (jsonify({"Error": "No load with this load_id exists"}), 404)

    # update the boat that the load is on, if any, before deleting the load, and return response
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

# put and delete routes for /boats/boat_id/loads/load_id
@app.route('/boats/<boat_id>/loads/<load_id>', methods=['PUT', 'DELETE'])
def boats_and_loads(boat_id, load_id):
  boat_key = client.key(constants.boats, int(boat_id))
  boat = client.get(key=boat_key)
  load_key = client.key(constants.loads, int(load_id))
  load = client.get(key=load_key)

  # assign a load to a boat
  if request.method == 'PUT':
    # if the boat or load does not exist, return 404
    if not boat or not load:
      return (jsonify({"Error": "The specified boat and/or load does not exist"}), 404)

    # if the load is already assigned to a boat, return 403
    elif load["carrier"] is not None:
      return (jsonify({"Error": "The load is already assigned to another boat"}), 403)

    # add the load to the boat, add boat to load's carrier, and return response
    else:
      boat["loads"].append({"id": str(load.key.id)})
      client.put(boat)

      load["carrier"] = {"id": str(boat_id), "name": boat["name"]}
      client.put(load)

      return ('', 204)
  
  # remove a load from a boat 
  elif request.method == 'DELETE':
    # if the boat or load does not exist, return 404
    if not boat or not load:
      return (jsonify({"Error": "The specified boat and/or load does not exist"}), 404)

    # iterate over boat's loads, and if the load is on the boat, remove the load from boat and update load's carrier and return response
    for loaded in boat["loads"]:
      if loaded["id"] == str(load.key.id):
        boat["loads"].remove(loaded)
        client.put(boat)
        load["carrier"] = None
        client.put(load)
        return ('', 204)

    # return 403 if the load is not on the boat
    return (jsonify({"Error": "No load with this load_id is at the boat with this boat_id"}), 403)

# Return 405 for requests not implemented herein, therefore not allowed
# reference: https://flask.palletsprojects.com/en/2.0.x/errorhandling/#error-handlers
@app.errorhandler(405)
def method_not_allowed(e):
  return (jsonify({"Error": "Method Not Allowed"}), 405)

if __name__ == '__main__':
  app.run(host='127.0.0.1', port=8080, debug=True)