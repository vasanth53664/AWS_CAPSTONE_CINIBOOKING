import uuid
import datetime
import qrcode
from io import BytesIO
from base64 import b64encode
from flask import Flask, render_template, session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'cinibooker_ultimate_edition_key'

# --- 1. THEATER CONFIGURATIONS (Dynamic Layouts) ---
THEATER_LAYOUTS = {
    'IMAX Phoenix': {'rows': 8, 'cols': 14, 'aisle': 7, 'label': 'IMAX 70mm'},
    'PVR Velachery': {'rows': 6, 'cols': 10, 'aisle': 5, 'label': 'AUDI 01'},
    'Rohini Silver Screens': {'rows': 10, 'cols': 16, 'aisle': 8, 'label': 'MAIN SCREEN'},
    'Luxe Cinemas': {'rows': 5, 'cols': 8, 'aisle': 4, 'label': 'LUXE'},
    'default': {'rows': 6, 'cols': 8, 'aisle': 4, 'label': 'SCREEN'}
}

# --- 2. MOVIE DATABASE ---
local_movies = [
    {
        'movie_id': '1', 'title': 'Leo', 'genre': 'Action/Thriller', 
        'theaters': ['PVR Velachery', 'Rohini Silver Screens'], 
        'showtimes': ['10:00 AM', '2:30 PM', '6:30 PM'], 'price': '190.00',
        'rating': '4.7',
        'poster': 'https://upload.wikimedia.org/wikipedia/en/7/71/Leo_2023_Indian_poster.jpg',
        'trailer': 'https://www.youtube.com/embed/Po3jStA673E'
    },
    {
        'movie_id': '2', 'title': 'Avatar: The Way of Water', 'genre': 'Sci-Fi/Adventure', 
        'theaters': ['IMAX Phoenix', 'Luxe Cinemas'], 
        'showtimes': ['11:00 AM', '5:00 PM', '9:00 PM'], 'price': '350.00',
        'rating': '4.9',
        'poster': 'https://upload.wikimedia.org/wikipedia/en/5/54/Avatar_The_Way_of_Water_poster.jpg',
        'trailer': 'https://www.youtube.com/embed/d9MyqFCD6sI'
    },
    {
        'movie_id': '3', 'title': 'Jailer', 'genre': 'Action/Comedy', 
        'theaters': ['PVR Velachery', 'Rohini Silver Screens'], 
        'showtimes': ['6:00 PM', '9:30 PM'], 'price': '150.00',
        'rating': '4.6',
        'poster': 'https://upload.wikimedia.org/wikipedia/en/c/cb/Jailer_2023_Tamil_film_poster.jpg',
        'trailer': 'https://www.youtube.com/embed/xenOe1ftNCa'
    }
]

local_users = {}
local_bookings = []

# --- 3. HELPERS ---
def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    return b64encode(buffered.getvalue()).decode("utf-8")

def get_occupied_seats(title, theater, date, time):
    occupied = []
    for b in local_bookings:
        # Strict matching: Bookings only overlap if ALL details match
        if (b['movie_title'] == title and b['theater'] == theater and b['date'] == date and b['time'] == time):
            occupied.extend([s.strip() for s in b['seats'].split(',')])
    return occupied

def get_next_3_days():
    return [(datetime.datetime.now() + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

# --- 4. ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', movies=local_movies, user=session['username'])

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in local_movies if str(m['movie_id']) == str(movie_id)), None)
    if not movie: return "Movie Not Found", 404
    return render_template('booking.html', movie=movie, dates=get_next_3_days())

# API for Dynamic Layout & Occupancy
@app.route('/api/seats')
def get_seats_api():
    occupied = get_occupied_seats(
        request.args.get('title'), request.args.get('theater'), 
        request.args.get('date'), request.args.get('time')
    )
    # Fetch specific layout for theater, or fallback to default
    layout = THEATER_LAYOUTS.get(request.args.get('theater'), THEATER_LAYOUTS['default'])
    return jsonify({'occupied': occupied, 'layout': layout})

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        d = request.form
        booking_id = str(uuid.uuid4())[:8]
        local_bookings.append({
            'booking_id': booking_id, 'username': session['username'],
            'movie_title': d['movie_title'], 'theater': d['theater'],
            'date': d['date'], 'time': d['time'], 'seats': ", ".join(d.getlist('seats')),
            'price': d['total_price']
        })
        return redirect(url_for('success'))
    
    # Render Payment Page
    seats = request.args.getlist('seats')
    if not seats: return redirect(url_for('dashboard'))
    total = len(seats) * float(request.args.get('price', 0))
    return render_template('payment.html', 
                           movie_title=request.args.get('movie_title'), 
                           theater=request.args.get('theater'),
                           date=request.args.get('date'), time=request.args.get('time'),
                           seats=seats, total=total)

@app.route('/success')
def success(): return render_template('success.html')

@app.route('/my_tickets')
def my_tickets():
    if 'username' not in session: return redirect(url_for('login'))
    user_bookings = [b for b in local_bookings if b['username'] == session['username']]
    
    # Enrich data for the ticket stub
    for b in user_bookings:
        m = next((m for m in local_movies if m['title'] == b['movie_title']), None)
        b['poster'] = m['poster'] if m else ''
        b['qr_code'] = generate_qr(f"ID:{b['booking_id']}|{b['movie_title']}|{b['seats']}")
        
    return render_template('my_tickets.html', bookings=user_bookings)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form['username']
        if u in local_users: return render_template('signup.html', error="Username taken")
        local_users[u] = {'password': generate_password_hash(request.form['password']), 'mobile': request.form['mobile']}
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        if u in local_users and check_password_hash(local_users[u]['password'], p):
            session['username'] = u
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

if __name__ == '__main__': app.run(debug=True, port=5000)