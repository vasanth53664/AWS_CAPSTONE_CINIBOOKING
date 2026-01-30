import uuid
import datetime
import re
import qrcode
from io import BytesIO
from base64 import b64encode
from flask import Flask, render_template, session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'local_ultimate_key'

# --- 1. LOCAL STORAGE ---
local_users = {}
local_bookings = []
local_movies = [
    {'movie_id': '1', 'title': 'Master (Re-Release)', 'genre': 'Action', 'theaters': ['PVR Velachery'], 'time': '6:00 PM', 'price': '150.00'},
    {'movie_id': '2', 'title': 'Interstellar', 'genre': 'Sci-Fi', 'theaters': ['IMAX Phoenix'], 'time': '9:30 PM', 'price': '250.00'},
    {'movie_id': '3', 'title': 'Viduthalai Part 2', 'genre': 'Drama', 'theaters': ['Rohini Silver Screens'], 'time': '11:00 AM', 'price': '120.00'}
]
admin_users = {'admin': 'password123'}

# --- 2. HELPERS (QR, VALIDATION, ANALYTICS) ---
def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    return b64encode(buffered.getvalue()).decode("utf-8")

def is_valid_luhn(n):
    """Validates Credit Card Numbers"""
    n = n.replace(" ", "")
    if not n.isdigit(): return False
    t=0; r=n[::-1]
    for i,d in enumerate(r):
        x=int(d)
        if i%2==1: x*=2; 
        if x>9: x-=9
        t+=x
    return t%10==0

def get_analytics():
    """Calculates Revenue for Admin"""
    total_rev = sum(float(b['price']) for b in local_bookings)
    total_tix = len(local_bookings)
    return {'revenue': f"₹{total_rev:,.2f}", 'tickets': total_tix}

def get_occupied_seats(movie_title):
    occupied = []
    for b in local_bookings:
        if b['movie_title'] == movie_title:
            occupied.extend([s.strip() for s in b['seats'].split(',')])
    return occupied

# --- 3. CORE LOGIC ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    # 1. Search Logic
    movies = local_movies
    query = request.args.get('q')
    if query:
        q = query.lower()
        movies = [m for m in movies if q in m['title'].lower() or q in m['genre'].lower()]
    
    # 2. Analytics (Admin Only)
    stats = get_analytics() if session.get('is_admin') else None
    
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'), analytics=stats)

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in local_movies if str(m['movie_id']) == str(movie_id)), None)
    return render_template('booking.html', movie=movie, occupied_seats=get_occupied_seats(movie['title']))

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        d = request.form
        # 3. Payment Validation
        if d['payment_method'] == 'card' and not is_valid_luhn(d['card_number']):
            return render_template('payment.html', error="Invalid Card Number", **d)
        
        booking_id = str(uuid.uuid4())[:8]
        local_bookings.append({
            'booking_id': booking_id, 'username': session['username'],
            'movie_title': d['movie_title'], 'theater': d['theater'],
            'seats': ", ".join(d.getlist('seats')), 'price': d['total_price'],
            'date': datetime.datetime.now().strftime("%Y-%m-%d")
        })
        print(f"\n[🔔 LOCAL SMS] Booking Confirmed! ID: {booking_id}\n")
        return redirect(url_for('success'))

    seats = request.args.getlist('seats')
    total = len(seats) * float(request.args.get('price', 0))
    return render_template('payment.html', movie_title=request.args.get('movie_title'), 
                           theater=request.args.get('theater'), seats=seats, total=total)

@app.route('/success')
def success(): return render_template('success.html')

@app.route('/my_tickets')
def my_tickets():
    if 'username' not in session: return redirect(url_for('login'))
    user_bookings = [b for b in local_bookings if b['username'] == session['username']]
    for b in user_bookings:
        b['qr_code'] = generate_qr(f"ID:{b['booking_id']}|Movie:{b['movie_title']}")
    return render_template('my_tickets.html', bookings=user_bookings)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form['username']
        if u in local_users: return render_template('signup.html', error="User Exists")
        local_users[u] = {'password': generate_password_hash(request.form['password']), 'mobile': request.form['mobile']}
        print(f"\n[🔔 LOCAL SMS] Welcome {u}!\n")
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        if u == 'admin' and p == 'password123':
            session['username'], session['is_admin'] = u, True
            return redirect(url_for('dashboard'))
        if u in local_users and check_password_hash(local_users[u]['password'], p):
            session['username'], session['is_admin'] = u, False
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Login")
    return render_template('login.html')

@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Denied", 403
    if request.method == 'POST':
        local_movies.append({
            'movie_id': str(uuid.uuid4()), 'title': request.form['title'],
            'genre': request.form['genre'], 'theaters': request.form['theaters'].split(','),
            'time': request.form['time'], 'price': request.form['price']
        })
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

if __name__ == '__main__': app.run(debug=True, port=5000)