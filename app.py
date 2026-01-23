import uuid
import datetime
import re
import qrcode
from io import BytesIO
from base64 import b64encode
from flask import Flask, render_template, session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION SWITCH ---
# False = Runs on your laptop (RAM). True = Runs on AWS (DynamoDB).
USE_AWS = False 

app = Flask(__name__)
app.secret_key = 'movie_magic_qr_edition'

# --- 1. AWS SETUP ---
if USE_AWS:
    import boto3
    from botocore.exceptions import ClientError
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    users_table = dynamodb.Table('MovieMagic_Users')
    movies_table = dynamodb.Table('MovieMagic_Movies')
    bookings_table = dynamodb.Table('MovieMagic_Bookings')
    print("✅ RUNNING IN AWS MODE")

# --- 2. LOCAL SETUP ---
else:
    local_users = {} 
    local_bookings = []
    local_movies = [
        {
            'movie_id': '1', 'title': 'Interstellar Return', 'genre': 'Sci-Fi',
            'theaters': ['IMAX City Center', 'PVR Grand Mall'], 'time': '7:00 PM', 'price': '15.00'
        },
        {
            'movie_id': '2', 'title': 'The Cyberpunk Era', 'genre': 'Action',
            'theaters': ['PVR Grand Mall', 'Inox Forum'], 'time': '9:30 PM', 'price': '12.50'
        }
    ]
    print("💻 RUNNING IN LOCAL MODE")

admin_users = {'admin': 'password123', 'thiru': 'mysecretpass'}

# --- QR CODE GENERATOR ---
def generate_qr(data):
    """Creates a QR code and returns it as a Base64 string for HTML"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered)
    return b64encode(buffered.getvalue()).decode("utf-8")

# --- VALIDATION HELPERS ---
def is_strong_password(password):
    if len(password) < 8: return False, "Password must be 8+ chars."
    if not re.search(r"\d", password): return False, "Password must have a number."
    if not re.search(r"[!@#$%^&*]", password): return False, "Password must have a special symbol."
    return True, None

def is_valid_contact(email, mobile):
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email): return False, "Invalid Email."
    if not re.match(r"^\d{10}$", mobile): return False, "Mobile must be 10 digits."
    return True, None

def is_valid_luhn(card_number):
    card_number = card_number.replace(" ", "")
    if not card_number.isdigit(): return False
    total = 0; reverse = card_number[::-1]
    for i, digit in enumerate(reverse):
        n = int(digit)
        if i % 2 == 1: n *= 2
        if n > 9: n -= 9
        total += n
    return total % 10 == 0

# --- DATABASE HELPERS ---
def get_all_movies():
    if USE_AWS:
        try: return movies_table.scan().get('Items', [])
        except: return []
    else: return local_movies

def get_occupied_seats(movie_title):
    occupied = []
    source = []
    if USE_AWS:
        try: source = bookings_table.scan().get('Items', [])
        except: pass
    else: source = local_bookings
    
    for b in source:
        if b.get('movie_title') == movie_title:
            occupied.extend([s.strip() for s in b['seats'].split(',')])
    return occupied

def create_user(data):
    u = data['username']
    # Hash Password
    p = generate_password_hash(data['password'])
    record = {'username': u, 'password': p, 'email': data['email'], 'mobile': data['mobile']}
    
    if USE_AWS:
        try:
            if 'Item' in users_table.get_item(Key={'username': u}): return False
            users_table.put_item(Item=record)
        except: return False
    else:
        if u in local_users: return False
        local_users[u] = record
    return True

def check_login(u, p):
    if u in admin_users and admin_users[u] == p: return True, True
    
    stored = None
    if USE_AWS:
        try:
            resp = users_table.get_item(Key={'username': u})
            if 'Item' in resp: stored = resp['Item']
        except: pass
    else: stored = local_users.get(u)

    if stored and check_password_hash(stored['password'], p): return True, False
    return False, False

def save_booking(data):
    record = {
        'booking_id': str(uuid.uuid4()),
        'username': session['username'],
        'movie_title': data['movie_title'],
        'theater': data['theater'],
        'seats': ", ".join(data.getlist('seats')),
        'date': datetime.datetime.now().strftime("%Y-%m-%d"),
        'price': str(data['total_price']),
        'method': data['payment_method'].upper()
    }
    if USE_AWS: bookings_table.put_item(Item=record)
    else: local_bookings.append(record)

def get_user_history_with_qr(username):
    source = []
    if USE_AWS:
        try: source = bookings_table.scan().get('Items', [])
        except: pass
    else: source = local_bookings
    
    # Filter for user
    user_bookings = [b for b in source if b['username'] == username]
    
    # Add QR Code to each ticket
    for ticket in user_bookings:
        qr_text = f"ID: {ticket['booking_id']} | Movie: {ticket['movie_title']} | Seats: {ticket['seats']}"
        ticket['qr_code'] = generate_qr(qr_text)
        
    return user_bookings

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    movies = get_all_movies()
    movies.sort(key=lambda x: x.get('title'))
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'))

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in get_all_movies() if str(m['movie_id']) == str(movie_id)), None)
    if not movie: return "Movie Not Found", 404
    return render_template('booking.html', movie=movie, occupied_seats=get_occupied_seats(movie['title']))

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        data = request.form
        error = None
        if data['payment_method'] == 'card':
            if not is_valid_luhn(data['card_number']): error = "Invalid Card Number"
            elif not re.match(r'^\d{3}$', data['cvv']): error = "Invalid CVV"
        elif data['payment_method'] == 'upi':
            if '@' not in data['upi_id']: error = "Invalid UPI ID"
            
        if error:
            return render_template('payment.html', movie_title=data['movie_title'], theater=data['theater'], 
                                   seats=data.getlist('seats'), total=data['total_price'], error=error)
        save_booking(data)
        return redirect(url_for('success'))

    # GET
    seats = request.args.getlist('seats')
    if not seats: return redirect(url_for('dashboard'))
    total = len(seats) * float(request.args.get('price', 0))
    return render_template('payment.html', movie_title=request.args.get('movie_title'), 
                           theater=request.args.get('theater'), seats=seats, total=total)

@app.route('/success')
def success(): return render_template('success.html')

@app.route('/my_tickets')
def my_tickets():
    if 'username' not in session: return redirect(url_for('login'))
    # Fetch tickets AND generate QR codes
    bookings = get_user_history_with_qr(session['username'])
    return render_template('my_tickets.html', bookings=bookings)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Validations
        is_strong, msg = is_strong_password(request.form['password'])
        if not is_strong: return render_template('signup.html', error=msg)
        
        is_valid, msg = is_valid_contact(request.form['email'], request.form['mobile'])
        if not is_valid: return render_template('signup.html', error=msg)
        
        if create_user(request.form): return redirect(url_for('login'))
        return render_template('signup.html', error="Username taken!")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        success, is_admin = check_login(request.form['username'], request.form['password'])
        if success:
            session['username'] = request.form['username']
            session['is_admin'] = is_admin
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Access Denied", 403
    if request.method == 'POST':
        d = request.form
        m = {'movie_id': str(uuid.uuid4()), 'title': d['title'], 'genre': d['genre'], 
             'theaters': [t.strip() for t in d['theaters'].split(',')], 'time': d['time'], 'price': str(d['price'])}
        if USE_AWS: movies_table.put_item(Item=m)
        else: local_movies.append(m)
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)