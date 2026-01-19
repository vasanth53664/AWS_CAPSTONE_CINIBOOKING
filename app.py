from flask import Flask, render_template, session, redirect, url_for, request

app = Flask(__name__)
app.secret_key = 'movie_magic_secure'

# --- 1. ADMIN CONFIG ---
admin_users = {
    'admin': 'password123',
    'thiru': 'mysecretpass'
}

# --- 2. USER DATABASE (Temporary Memory) ---
# Stores registered users. Format: {'john': 'pass1', 'jane': 'pass2'}
users_db = {} 

# --- MOCK MOVIE DATA ---
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

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'))

# --- AUTHENTICATION LOGIC ---

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Check if user already exists
        if username in users_db or username in admin_users:
            return "Error: Username already exists! <a href='/signup'>Try again</a>"
        
        # Save new user to memory
        users_db[username] = password
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_input = request.form['username']
        pass_input = request.form['password']
        
        # 1. Check if Admin
        if user_input in admin_users and admin_users[user_input] == pass_input:
            session['username'] = user_input
            session['is_admin'] = True
            return redirect(url_for('dashboard'))
        
        # 2. Check if Registered User
        elif user_input in users_db and users_db[user_input] == pass_input:
            session['username'] = user_input
            session['is_admin'] = False
            return redirect(url_for('dashboard'))
            
        # 3. Invalid Credentials
        else:
            error = "Invalid Username or Password. Please Sign Up first."

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- ADMIN & BOOKING ROUTES ---
@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Access Denied", 403
    if request.method == 'POST':
        new_movie = {
            'id': len(movies) + 1,
            'title': request.form['title'],
            'genre': request.form['genre'],
            'theaters': [t.strip() for t in request.form['theaters'].split(',')],
            'time': request.form['time'],
            'price': float(request.form['price'])
        }
        movies.append(new_movie)
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

@app.route('/book/<int:movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movie = next((m for m in movies if m['id'] == movie_id), None)
    return render_template('booking.html', movie=movie)

@app.route('/payment')
def payment():
    return render_template('payment.html', total=15.00, theater=request.args.get('theater'))

@app.route('/success')
def success():
    return render_template('success.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)