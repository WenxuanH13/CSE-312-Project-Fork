from flask import Flask, render_template,request, send_from_directory,redirect,url_for,make_response,abort
from werkzeug.utils import secure_filename
from authentication import extract_credentials,validate_password,extract_credentialslogin
from db import db
import bcrypt
import hashlib
import secrets
import html
import extra
import os
from flask_socketio import  emit, SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import time


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get('SECRET_KEY')

socketio = SocketIO(app)

UPLOAD_FOLDER = 'static/images/'
ALLOWED_EXTENSIONS = {'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_client_ip():
    if "X-Real-IP" in request.headers:
        return request.headers.get("X-Real-IP")
    elif "X-Forwarded-For" in request.headers:
        return request.headers.get("X-Forwarded-For").split(",")[0]
    else:
        return request.remote_addr

limiter = Limiter(
        app=app, 
        key_func=get_client_ip,
        default_limits=['50 per 10 seconds'],
)

ip_address = {}

@app.after_request
def add_header(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(429)
def ratelimit_handler(e):
    ip = get_client_ip()
    block_ip(ip)
    return "Too Many Requests, try again later", 429

def is_ip_blocked(ip):
    return ip in ip_address and ip_address[ip] > time.time()

def block_ip(ip):
    ip_address[ip] = time.time() + 30


@app.route('/toggle-dark-mode')
def toggle_dark_mode():
    # Get the current dark mode preference from the cookie
    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == 'True':
        dark_mode = False
    else:
        dark_mode = True

    # Update the dark mode preference cookie with the new value
    resp = make_response(redirect('/'))
    resp.set_cookie('dark_mode', str(dark_mode))

    return resp
    
@app.route('/')
@limiter.limit("50 per 10 seconds")
def index():
    addy = get_client_ip()
    
    if is_ip_blocked(addy):
        return "Too Many Requests, try again later", 429

    auth_token = request.cookies.get("auth_token")

    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == "True":
        dark_mode = True
    else:
        dark_mode = False
    username = None
    # checks if user is logged in
    if auth_token:
        log = True
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        if(user != None):
            username = user['username']
            # check for posts and load posts
            if db.posts is not None:  #if there is a database
                data = db.posts.find({})
                return render_template("index.html", content_type='text/html', logged_in=log, data=data, username=username,dark_mode=dark_mode)  
            else:
                return render_template("index.html", content_type='text/html', logged_in=log, username=username,dark_mode=dark_mode)
    else:
        log = False
    #for guest page, check for posts and loads them
    if db.posts is not None:  #if there is a database
        data = db.posts.find({})
        return render_template("index.html", content_type='text/html', logged_in=log, data=data,dark_mode=dark_mode)
    
    return render_template("index.html", content_type='text/html', logged_in=log,dark_mode=dark_mode)

#takes the user to the register form
@app.route("/register")
def registerPath():
    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == 'True':
        dark_mode = True
    else:
        dark_mode = False
    return render_template('register.html', content_type='text/html',dark_mode=dark_mode)

#takes the user to the login form
@app.route("/login")
def loginPath():
    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == 'True':
        dark_mode = True
    else:
        dark_mode = False
    return render_template('login.html', content_type='text/html',dark_mode=dark_mode)

#takes the user to the post form
@app.route("/post")
def postPath():
    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == 'True':
        dark_mode = True
    else:
        dark_mode = False
    auth_token = request.cookies.get("auth_token")
    
    username = None
    # User must be logged in to post
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        if(user != None):
            username = user['username']

        return render_template('post.html', content_type='text/html', logged_in=True, username=username,dark_mode=dark_mode)
    else:
        return redirect('/login')
    
#takes the user to the global chat 
@app.route("/chat")
def chat():
    dark_mode = request.cookies.get('dark_mode')
    if dark_mode == 'True':
        dark_mode = True
    else:
        dark_mode = False
    auth_token = request.cookies.get("auth_token")
    username = None
    # User must be logged in to post
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        if(user != None):
            username = user['username']
        return render_template('global.html', content_type='text/html', logged_in=True, data=db.global_chat.find({}), username=username,dark_mode=dark_mode)
    else:
        return redirect('/login')
    
@app.route('/send-post', methods=['POST'])
def posting():
    app.logger.debug(request.files)
    
    # Access form data
    t = html.escape(request.form.get('title'))
    q = html.escape(request.form.get('question'))

    auth_token = request.cookies.get("auth_token")
    username = "Guest" # If shows up as Guest (something is broken)
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        username = user['username']

    file = request.files['file']
    type = file.filename.split(".",1)[1]
    file_count = len(os.listdir(app.config['UPLOAD_FOLDER']))
    
    if file:
        filename = secure_filename(f"userupload{file_count}.{type}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        


    if db.posts is not None:
        if db.posts.find_one({}) is None: 
            db.posts.insert_one({'title': t, "question": q, "username": username, "post_id": 1, "liked_users": [], "like_count": 0, 'file':filename})
            app.logger.debug(f"filename on db = {filename}")
        else:
            collections = list(db.posts.find({}))
            num = len(collections)
            db.posts.insert_one({'title': t, "question": q, "username": username, "post_id": num+1, "liked_users": [], "like_count": 0, 'file':filename})
            app.logger.debug(f"filename on db = {filename}")

    return redirect('/')

@app.route('/like/<post_id>', methods=['POST'])
def like(post_id):
    auth_token = request.cookies.get("auth_token")
    # checks if user is logged in
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        username = user['username']
        
        dbPost = db.posts.find_one({'post_id': int(post_id)})
        if username in dbPost['liked_users']:    #check if the user has liked the post (liking again == not liking)
            arr = dbPost['liked_users']
            arr.remove(username)
            updateM = {
                "$set": {
                    'title': dbPost['title'], 
                    "question": dbPost["question"], 
                    "username": dbPost["username"], 
                    "post_id": dbPost["post_id"], 
                    "liked_users": arr, 
                    "like_count": len(arr)
                    }
            }
            db.posts.update_one({'post_id': int(post_id)}, updateM)
        else: # if they have not liked or have unliked,they can like the post
            arr = dbPost['liked_users']
            arr.append(username)
            updateM = {
                "$set": {
                    'title': dbPost['title'], 
                    "question": dbPost["question"], 
                    "username": dbPost["username"], 
                    "post_id": dbPost["post_id"], 
                    "liked_users": arr, 
                    "like_count": len(arr)
                }
            }
            db.posts.update_one({'post_id': int(post_id)}, updateM)
        return redirect('/')
    else:
        return redirect('/login')

# Register user
@app.route('/auth-register', methods=['POST'])
def register():
    username, password1, password2 = extract_credentials(request)
    if password1 != password2:
        return "The entered passwords do not match"
    
    if not validate_password(password1):
        return 'Password does not meet the requirements'
    
    user = db.accounts.find_one({'username': username})
    if user:
        return "Username is taken"
    
    # Generate a salt
    salt = bcrypt.gensalt()
    
    # Hash the password with the salt
    hashed_password = bcrypt.hashpw(password1.encode('utf-8'), salt)
    
    # Store the username, hashed password, and salt in the database
    
    #REMEMBER TO REMOVE PASSWORD FIELD WHEN FINAL SUBMISSION
    data = {"username": username, "hash": hashed_password, "salt": salt}
    db.accounts.insert_one(data)
    
    return redirect(url_for('loginPath'))

@app.route('/auth-login', methods=['POST'])
def login():
    username, password = extract_credentialslogin(request)

    # Retrieve user from database
    user = db.accounts.find_one({'username': username})

    if user:
        salt = user['salt']
        hash = bcrypt.hashpw(password.encode('utf-8'),salt)

        if(hash == user["hash"]):
            token = secrets.token_hex(16)
            hashed_token = hashlib.sha256(token.encode()).hexdigest()
            db.accounts.update_one({'username':username},{'$set':{'token':hashed_token}})

            # Create a response object
            resp = make_response(redirect('/'))  # Redirect to the homepage

            # Set the token as a cookie
            resp.set_cookie('auth_token', token, httponly=True, max_age=3600)  # Expires in 1 hour

            return resp

    return 'Invalid username or password'

@app.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get("auth_token")
    hashed_token = hashlib.sha256(token.encode()).hexdigest()
    
    db.accounts.update_one({"token": hashed_token},{"$unset":{"token":""}})

    resp = make_response(redirect('/'))

    resp.set_cookie('auth_token', '', expires=0)
    return resp

@app.route('/static/js/<path:filename>')
@limiter.limit("50 per 10 seconds")
def js(filename):   
    addy = get_client_ip()
    
    if is_ip_blocked(addy):
        return "Too Many Requests, try again later", 429
    
    return send_from_directory('static/js', filename, mimetype='text/javascript')

@app.route('/static/css/<path:filename>')
@limiter.limit("50 per 10 seconds")
def css(filename):
    addy = get_client_ip()
    
    if is_ip_blocked(addy):
        return "Too Many Requests, try again later", 429
    
    return send_from_directory('static/css', filename, mimetype='text/css')

@app.route('/static/image/<path:filename>')
def img(filename):
    splits = filename.split(".",1)
    mimetype = ""
    if splits[1] == "jpg":
        mimetype = "image/jpg"
    if splits[1] == "jpeg":
        mimetype = "image/jpeg"
    if splits[1] == "png":
        mimetype = "image/png"
    if splits[1] == "gif":
        mimetype = "image/gif"

    return send_from_directory('static/image', filename, mimetype=mimetype)

@socketio.on("sends")
@limiter.limit("50 per 10 seconds")
def sending(data):

    addy = get_client_ip()
    
    if is_ip_blocked(addy):
        return "Too Many Requests, try again later", 429
    
    auth_token = request.cookies.get("auth_token")

    username = None
    # checks if user is logged in
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        user = db.accounts.find_one({"token":hashed_token})
        if(user != None):
            username = user['username']
    
    if data["delay"] != 0 or data["delay"] != None or data["delay"] != "":
        timer = int(data["delay"])
        while timer > 0:
            emit("time_left", {"seconds": timer}, room=request.sid)
            time.sleep(1)
            timer -= 1

        if timer == 0:
            emit("time_left", {"seconds": 0}, room=request.sid)
        


    data["message"] = extra.escape_html(data["message"])
    emit("chat", {'username': username, 'message': data}, broadcast=True)
    db.global_chat.insert_one({'username': username, 'message': data})


if __name__ == '__main__':
    # app.run(debug=True, host='0.0.0.0', port=8080)
    socketio.run(app, debug=True, host='0.0.0.0', port=8080, allow_unsafe_werkzeug=True)
