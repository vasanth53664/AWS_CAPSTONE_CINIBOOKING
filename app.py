from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# --- In-Memory Database ---
users = {}          # Stores user credentials
admin_users = {}    # Stores admin credentials
movies = []         # Stores movie info: [{'id': 1, 'title': 'Avatar', 'slots': 100, 'price': 15}]
bookings = {}       # Stores bookings: {'username': [{'movie_title': 'Avatar', 'seats': 2}]}

# --- Core Routes ---
@app.route('/')
def index():
    # If logged in, go to dashboard, else show landing page
    if 'username' in session:
        return redirect(url_for('user_dashboard'))
    if 'admin' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('index.html', movies=movies) # Pass movies to index for visibility

@app.route('/about')
def about():
    return render_template('about.html')

# --- User Authentication ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users:
            return "User already exists!"
        users[username] = password
        bookings[username] = [] # Initialize empty booking list for new user
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and users[username] == password:
            session['username'] = username
            return redirect(url_for('user_dashboard'))
        return "Invalid credentials!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

# --- User Features (Booking) ---
@app.route('/dashboard')
def user_dashboard():
    if 'username' in session:
        user_bookings = bookings.get(session['username'], [])
        return render_template('home.html', username=session['username'], movies=movies, my_bookings=user_bookings)
    return redirect(url_for('login'))

@app.route('/book/<int:movie_id>', methods=['POST'])
def book_ticket(movie_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Simple booking logic
    seat_count = int(request.form.get('seats', 1))
    
    # Find movie
    for movie in movies:
        if movie['id'] == movie_id:
            if movie['slots'] >= seat_count:
                movie['slots'] -= seat_count
                
                # Save booking
                booking_details = {
                    'movie_title': movie['title'], 
                    'seats': seat_count, 
                    'total_cost': seat_count * movie['price']
                }
                bookings[session['username']].append(booking_details)
                return redirect(url_for('user_dashboard'))
            else:
                return "Not enough seats available!"
    
    return "Movie not found!"

# --- Admin Authentication ---
@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in admin_users:
            return "Admin already exists!"
        admin_users[username] = password
        return redirect(url_for('admin_login'))
    return render_template('admin_signup.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in admin_users and admin_users[username] == password:
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        return "Invalid admin credentials!"
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

# --- Admin Features (Manage Movies) ---
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        # Add a new movie
        title = request.form['title']
        slots = int(request.form['slots'])
        price = float(request.form['price'])
        new_id = len(movies) + 1
        
        movies.append({
            'id': new_id,
            'title': title,
            'slots': slots,
            'price': price
        })
        
    return render_template('admin_dashboard.html', username=session['admin'], movies=movies)

if __name__ == '__main__':
    app.run(debug=True, port=5000)