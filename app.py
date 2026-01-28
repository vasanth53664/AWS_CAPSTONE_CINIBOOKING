import uuid
import datetime
import re
import qrcode
from io import BytesIO
from base64 import b64encode
from flask import Flask, render_template, session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION SWITCH ---
# CHANGE THIS TO 'True' WHEN DEPLOYING TO AWS EC2
USE_AWS = True 
REGION = 'ap-south-1'

app = Flask(__name__)
app.secret_key = 'movie_magic_sns_edition'

# --- 1. AWS RESOURCES ---
if USE_AWS:
    import boto3
    # DynamoDB Setup
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    users_table = dynamodb.Table('MovieMagic_Users')
    movies_table = dynamodb.Table('MovieMagic_Movies')
    bookings_table = dynamodb.Table('MovieMagic_Bookings')
    
    # SNS Setup (For SMS)
    sns_client = boto3.client('sns', region_name=REGION)
    print("✅ RUNNING IN AWS MODE (DB + SNS)")
else:
    # Local Data Storage
    local_users = {} 
    local_bookings = []
    local_movies = [
        {'movie_id': '1', 'title': 'Interstellar Return', 'genre': 'Sci-Fi', 'theaters': ['IMAX City'], 'time': '7:00 PM', 'price': '15.00'},
        {'movie_id': '2', 'title': 'The Cyberpunk Era', 'genre': 'Action', 'theaters': ['PVR Grand'], 'time': '9:30 PM', 'price': '12.50'}
    ]
    print("💻 RUNNING IN LOCAL MODE")

admin_users = {'admin': 'password123'}

# --- 2. HELPER FUNCTIONS ---

def send_sms(mobile, message):
    """Sends SMS via AWS SNS if in Cloud Mode, otherwise prints to console."""
    if USE_AWS:
        try:
            # AWS requires E.164 format (e.g., +919999999999)
            phone_number = mobile if mobile.startswith('+') else f"+91{mobile}" 
            sns_client.publish(PhoneNumber=phone_number, Message=f"MovieMagic: {message}")
            print(f"📲 SMS sent to {phone_number}")
        except Exception as e:
            print(f"❌ SMS Failed: {e}")
    else:
        print(f"\n[LOCAL SMS SIMULATION] To: {mobile} | Msg: {message}\n")

def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    return b64encode(buffered.getvalue()).decode("utf-8")

def get_all_movies():
    if USE_AWS:
        try: return movies_table.scan().get('Items', [])
        except: return []
    else: return local_movies

def get_analytics():
    """Calculates Revenue and Sales for Admin"""
    source = []
    if USE_AWS:
        try: source = bookings_table.scan().get('Items', [])
        except: pass
    else: source = local_bookings
    
    total_rev = sum(float(b['price']) for b in source)
    total_tix = len(source)
    
    counts = {}
    for b in source:
        t = b['movie_title']
        counts[t] = counts.get(t, 0) + 1
    top_movie = max(counts, key=counts.get) if counts else "None"
    
    return {'revenue': f"${total_rev:,.2f}", 'tickets': total_tix, 'top_movie': top_movie}

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
    
    # Send Welcome SMS
    send_sms(data['mobile'], f"Welcome {u}! Your MovieMagic account is ready.")
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
    booking_id = str(uuid.uuid4())[:8]
    record = {
        'booking_id': booking_id,
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
    
    # Retrieve User Mobile for SMS
    user_mobile = "0000000000"
    if USE_AWS:
        try:
            u_data = users_table.get_item(Key={'username': session['username']})
            if 'Item' in u_data: user_mobile = u_data['Item']['mobile']
        except: pass
    elif session['username'] in local_users:
        user_mobile = local_users[session['username']]['mobile']
        
    send_sms(user_mobile, f"Confirmed! {data['movie_title']} ({record['seats']}). ID: {booking_id}")

def get_user_history_with_qr(username):
    source = []
    if USE_AWS:
        try: source = bookings_table.scan().get('Items', [])
        except: pass
    else: source = local_bookings
    
    user_bookings = [b for b in source if b['username'] == username]
    for ticket in user_bookings:
        qr_text = f"ID:{ticket['booking_id']}|Movie:{ticket['movie_title']}|Seats:{ticket['seats']}"
        ticket['qr_code'] = generate_qr(qr_text)
    return user_bookings

# --- VALIDATORS ---
def is_strong_password(p):
    return len(p) >= 8 and re.search(r"\d", p) and re.search(r"[!@#$%^&*]", p)

def is_valid_contact(e, m):
    return re.match(r"[^@]+@[^@]+\.[^@]+", e) and re.match(r"^\d{10}$", m)

def is_valid_luhn(n):
    n = n.replace(" ", "")
    if not n.isdigit(): return False
    t=0; r=n[::-1]
    for i,d in enumerate(r):
        x=int(d)
        if i%2==1: x*=2; 
        if x>9: x-=9
        t+=x
    return t%10==0

# --- ROUTES ---

@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    movies = get_all_movies()
    
    # Search Logic
    query = request.args.get('q')
    if query:
        q = query.lower()
        movies = [m for m in movies if q in m['title'].lower() or q in m['genre'].lower()]
    
    movies.sort(key=lambda x: x.get('title'))
    analytics = get_analytics() if session.get('is_admin') else None
    
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'), analytics=analytics)

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in get_all_movies() if str(m['movie_id']) == str(movie_id)), None)
    if not movie: return "Not Found", 404
    return render_template('booking.html', movie=movie, occupied_seats=get_occupied_seats(movie['title']))

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        d = request.form
        err = None
        if d['payment_method'] == 'card':
            if not is_valid_luhn(d['card_number']): err="Invalid Card"
            elif not re.match(r'^\d{3}$', d['cvv']): err="Invalid CVV"
        elif d['payment_method'] == 'upi':
            if '@' not in d['upi_id']: err="Invalid UPI"
        
        if err: return render_template('payment.html', movie_title=d['movie_title'], theater=d['theater'], 
                                       seats=d.getlist('seats'), total=d['total_price'], error=err)
        save_booking(d)
        return redirect(url_for('success'))

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
    return render_template('my_tickets.html', bookings=get_user_history_with_qr(session['username']))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        if not is_strong_password(request.form['password']): return render_template('signup.html', error="Weak Password (Need 8 chars, number, symbol)")
        if not is_valid_contact(request.form['email'], request.form['mobile']): return render_template('signup.html', error="Invalid Email or Mobile (10 digits)")
        if create_user(request.form): return redirect(url_for('login'))
        return render_template('signup.html', error="User Exists")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        suc, admin = check_login(request.form['username'], request.form['password'])
        if suc:
            session['username'] = request.form['username']
            session['is_admin'] = admin
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Denied", 403
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