import uuid
import datetime
from flask import Flask, render_template, session, redirect, url_for, request
import re
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION ---
USE_AWS = False 

app = Flask(__name__)
app.secret_key = 'movie_magic_secure_v2'

# --- 1. AWS SETUP ---
if USE_AWS:
    import boto3
    from botocore.exceptions import ClientError
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    users_table = dynamodb.Table('MovieMagic_Users')
    movies_table = dynamodb.Table('MovieMagic_Movies')
    bookings_table = dynamodb.Table('MovieMagic_Bookings')
    print("✅ RUNNING IN AWS MODE")
else:
    # UPDATED: Local Users now stores a DICTIONARY, not just a string
    # Structure: {'thiru': {'password': 'hash', 'email': 't@g.com', 'mobile': '999...'}}
    local_users = {} 
    local_bookings = []
    local_movies = [
        {'movie_id': '1', 'title': 'Interstellar Return', 'genre': 'Sci-Fi', 'theaters': ['IMAX City Center'], 'time': '7:00 PM', 'price': '15.00'}
    ]
    print("💻 RUNNING IN LOCAL MODE")

admin_users = {'admin': 'password123', 'thiru': 'mysecretpass'}

# --- VALIDATION HELPERS ---
def is_strong_password(password):
    if len(password) < 8: return False, "Password must be at least 8 chars."
    if not re.search(r"\d", password): return False, "Password must contain a number."
    if not re.search(r"[!@#$%^&*]", password): return False, "Password must contain a special char."
    return True, None

def is_valid_contact(email, mobile):
    # Regex for Email (e.g., name@domain.com)
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False, "Invalid Email Address format."
    
    # Regex for Mobile (10 digits)
    if not re.match(r"^\d{10}$", mobile):
        return False, "Mobile number must be exactly 10 digits."
    
    return True, None

def check_login(username, password):
    # 1. Admin Check
    if username in admin_users and admin_users[username] == password:
        return True, True

    # 2. User Check
    stored_data = None
    if USE_AWS:
        try:
            resp = users_table.get_item(Key={'username': username})
            if 'Item' in resp: stored_data = resp['Item']
        except: pass
    else:
        stored_data = local_users.get(username)

    # Verify Hash
    if stored_data and check_password_hash(stored_data['password'], password):
        return True, False
    
    return False, False

def create_user(data):
    username = data['username']
    password = generate_password_hash(data['password']) # Hash it!
    email = data['email']
    mobile = data['mobile']

    user_record = {
        'username': username,
        'password': password,
        'email': email,
        'mobile': mobile
    }

    if USE_AWS:
        try:
            if 'Item' in users_table.get_item(Key={'username': username}): return False
            users_table.put_item(Item=user_record)
        except: return False
    else:
        if username in local_users: return False
        local_users[username] = user_record # Save full record
    return True

# --- EXISTING HELPERS (Keep these unchanged) ---
def get_all_movies():
    if USE_AWS:
        try: return movies_table.scan().get('Items', [])
        except: return []
    else: return local_movies

def add_movie_to_db(data):
    new_movie = {
        'movie_id': str(uuid.uuid4()), 'title': data['title'], 'genre': data['genre'],
        'theaters': [t.strip() for t in data['theaters'].split(',')], 'time': data['time'], 'price': str(data['price'])
    }
    if USE_AWS: movies_table.put_item(Item=new_movie)
    else: local_movies.append(new_movie)

def is_valid_luhn(card_number):
    card_number = card_number.replace(" ", "")
    if not card_number.isdigit(): return False
    total = 0; reverse = card_number[::-1]
    for i, digit in enumerate(reverse):
        n = int(digit)
        if i % 2 == 1: n *= 2; 
        if n > 9: n -= 9
        total += n
    return total % 10 == 0

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', movies=get_all_movies(), is_admin=session.get('is_admin'))

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in get_all_movies() if str(m['movie_id']) == str(movie_id)), None)
    return render_template('booking.html', movie=movie, occupied_seats=[]) # Simplified for brevity

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        form = request.form
        
        # 1. Validate Password Strength
        is_strong, pw_msg = is_strong_password(form['password'])
        if not is_strong: return render_template('signup.html', error=pw_msg)

        # 2. Validate Email & Mobile
        is_valid, contact_msg = is_valid_contact(form['email'], form['mobile'])
        if not is_valid: return render_template('signup.html', error=contact_msg)

        # 3. Create User
        if create_user(form):
            return redirect(url_for('login'))
        else:
            return render_template('signup.html', error="Username already exists!")
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        success, is_admin = check_login(request.form['username'], request.form['password'])
        if success:
            session['username'] = request.form['username']
            session['is_admin'] = is_admin
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

# Keep other routes (payment, success, my_tickets, admin) same as before...
# For brevity, I am not repeating them, but assume they exist below:
@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Access Denied", 403
    if request.method == 'POST': add_movie_to_db(request.form); return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)