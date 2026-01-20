from flask import Flask, render_template, session, redirect, url_for, request
import datetime

app = Flask(__name__)
app.secret_key = 'movie_magic_secure_key'

# --- 1. ADMIN CREDENTIALS ---
# Login with these to see the "Add Movie" button
admin_users = {
    'admin': 'password123',
    'thiru': 'mysecretpass'
}

# --- 2. DATABASES (In-Memory Storage) ---
# users_db stores registered users: {'username': 'password'}
users_db = {} 

# bookings_db stores ticket history (Matches your ER Diagram "Bookings" entity)
bookings_db = [] 

# movies list (Matches your ER Diagram "Movies" entity)
movies = [
    {
        'id': 1,
        'title': 'Interstellar Return',
        'genre': 'Sci-Fi',
        'theaters': ['IMAX City Center', 'PVR Grand Mall'],
        'time': '7:00 PM',
        'price': 15.00
    },
    {
        'id': 2,
        'title': 'The Cyberpunk Era',
        'genre': 'Action',
        'theaters': ['PVR Grand Mall', 'Inox Forum'],
        'time': '9:30 PM',
        'price': 12.50
    }
]

# --- PUBLIC ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

# --- DASHBOARD & MOVIES ---
@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'))

@app.route('/book/<int:movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    # Find the specific movie by ID
    movie = next((m for m in movies if m['id'] == movie_id), None)
    return render_template('booking.html', movie=movie)

# --- PAYMENT & BOOKING LOGIC ---
@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))

    # STEP 2: SAVE BOOKING (When user clicks "Pay")
    if request.method == 'POST':
        movie_title = request.form['movie_title']
        theater = request.form['theater']
        
        # Create a new booking record (ER Diagram Logic)
        new_booking = {
            'booking_id': len(bookings_db) + 1,
            'username': session['username'],
            'movie': movie_title,
            'theater': theater,
            'seats': 'A4, A5', # Placeholder (Future: get from form)
            'date': datetime.date.today().strftime("%Y-%m-%d"),
            'price': 15.00
        }
        bookings_db.append(new_booking) # Save to database
        return redirect(url_for('success'))

    # STEP 1: SHOW PAYMENT PAGE (Get details from Booking page)
    movie_title = request.args.get('movie_title')
    theater = request.args.get('theater')
    return render_template('payment.html', total=15.00, movie_title=movie_title, theater=theater)

@app.route('/success')
def success():
    return render_template('success.html')

@app.route('/my_tickets')
def my_tickets():
    if 'username' not in session: return redirect(url_for('login'))
    # Filter: Show only this user's tickets
    user_bookings = [b for b in bookings_db if b['username'] == session['username']]
    return render_template('my_tickets.html', bookings=user_bookings)

# --- ADMIN ROUTES ---
@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    # Security Check
    if not session.get('is_admin'): return "Access Denied", 403

    if request.method == 'POST':
        new_movie = {
            'id': len(movies) + 1,
            'title': request.form['title'],
            'genre': request.form['genre'],
            # Split comma-separated string into a list
            'theaters': [t.strip() for t in request.form['theaters'].split(',')],
            'time': request.form['time'],
            'price': float(request.form['price'])
        }
        movies.append(new_movie)
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

# --- AUTHENTICATION ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users_db:
            return "User exists!"
        users_db[username] = password
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        
        # Check Admin
        if user in admin_users and admin_users[user] == pw:
            session['username'] = user
            session['is_admin'] = True
            return redirect(url_for('dashboard'))
        
        # Check Regular User
        elif user in users_db and users_db[user] == pw:
            session['username'] = user
            session['is_admin'] = False
            return redirect(url_for('dashboard'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # host='0.0.0.0' allows mobile phones on the same Wi-Fi to connect
    app.run(debug=True, host='0.0.0.0', port=5000)