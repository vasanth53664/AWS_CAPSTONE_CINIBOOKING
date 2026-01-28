import uuid
import datetime
import boto3
from flask import Flask, render_template, session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash
from boto3.dynamodb.conditions import Key

app = Flask(__name__)
app.secret_key = 'lab_mission_success'

# --- LAB CONFIGURATION ---
# Set to True because we are deploying to EC2
USE_AWS = True
# Labs usually require 'us-east-1'. If your lab is specifically in Mumbai, change to 'ap-south-1'
REGION = 'us-east-1' 

# --- AWS SETUP ---
if USE_AWS:
    try:
        # 1. Connect to DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        users_table = dynamodb.Table('MovieMagic_Users')
        movies_table = dynamodb.Table('MovieMagic_Movies')
        bookings_table = dynamodb.Table('MovieMagic_Bookings')

        # 2. Connect to SNS
        sns_client = boto3.client('sns', region_name=REGION)
        print(f"✅ CONNECTED TO AWS in {REGION}")
    except Exception as e:
        print(f"⚠️ AWS CONNECTION ERROR: {e}")
        print("Did you attach the 'custom_user_role' to the EC2 instance?")

# --- LOCAL BACKUP DATA (For testing without AWS) ---
local_movies = [
    {'movie_id': '1', 'title': 'Lab Test Movie', 'genre': 'Action', 'theaters': ['Grand Rex'], 'time': '10:00 AM', 'price': '10.00'}
]
local_users = {}
local_bookings = []

# --- HELPER FUNCTIONS ---

def get_sns_topic_arn():
    # REPLACE THE TEXT BELOW WITH YOUR COPIED ARN
    return "arn:aws:sns:us-east-1:216989116084:MovieMagicTopic:24413a5a-c366-4347-80ab-9c1e78b78d26"

def send_notification(subject, message):
    """Publishes a message to the SNS Topic (Emails all subscribers)."""
    if USE_AWS:
        try:
            topic_arn = get_sns_topic_arn()
            if topic_arn:
                sns_client.publish(
                    TopicArn=topic_arn,
                    Subject=subject,
                    Message=message
                )
                print(f"📲 SNS Notification Sent: {subject}")
            else:
                print("⚠️ No SNS Topic found. Skipping notification.")
        except Exception as e:
            print(f"❌ SNS Failed: {e}")
    else:
        print(f"🔔 [LOCAL LOG] {subject}: {message}")

def get_all_movies():
    if USE_AWS:
        try:
            return movies_table.scan().get('Items', [])
        except: return []
    return local_movies

def create_user(data):
    u = data['username']
    p = generate_password_hash(data['password'])
    record = {'username': u, 'password': p, 'email': data['email'], 'mobile': data['mobile']}
    
    if USE_AWS:
        try:
            # Check if user exists
            if 'Item' in users_table.get_item(Key={'username': u}): return False
            users_table.put_item(Item=record)
        except: return False
    else:
        local_users[u] = record
    
    # NOTIFY VIA SNS
    send_notification("New User Signup", f"Welcome to MovieMagic, {u}!")
    return True

def check_login(u, p):
    # Admin backdoor for testing
    if u == 'admin' and p == 'password123': return True, True
    
    stored = None
    if USE_AWS:
        try:
            resp = users_table.get_item(Key={'username': u})
            if 'Item' in resp: stored = resp['Item']
        except: pass
    else:
        stored = local_users.get(u)

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
        'method': data['payment_method']
    }
    
    if USE_AWS:
        bookings_table.put_item(Item=record)
    else:
        local_bookings.append(record)
    
    # NOTIFY VIA SNS
    msg = f"Booking Confirmed!\nMovie: {data['movie_title']}\nSeats: {record['seats']}\nID: {booking_id}"
    send_notification("Ticket Confirmation", msg)

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    movies = get_all_movies()
    return render_template('dashboard.html', movies=movies)

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movies = get_all_movies()
    movie = next((m for m in movies if str(m['movie_id']) == str(movie_id)), None)
    return render_template('booking.html', movie=movie, occupied_seats=[])

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        save_booking(request.form)
        return redirect(url_for('success'))

    seats = request.args.getlist('seats')
    total = len(seats) * float(request.args.get('price', 0))
    return render_template('payment.html', 
                         movie_title=request.args.get('movie_title'), 
                         theater=request.args.get('theater'), 
                         seats=seats, total=total)

@app.route('/success')
def success(): return render_template('success.html')

@app.route('/my_tickets')
def my_tickets():
    if 'username' not in session: return redirect(url_for('login'))
    bookings = []
    if USE_AWS:
        # Scan is inefficient but fine for labs
        all_bookings = bookings_table.scan().get('Items', [])
        bookings = [b for b in all_bookings if b['username'] == session['username']]
    return render_template('my_tickets.html', bookings=bookings)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        if create_user(request.form): return redirect(url_for('login'))
        return render_template('signup.html', error="User already exists")
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        success, is_admin = check_login(request.form['username'], request.form['password'])
        if success:
            session['username'] = request.form['username']
            session['is_admin'] = is_admin
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Login")
    return render_template('login.html')

@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    # Helper route to quickly add movies in AWS for testing
    if request.method == 'POST':
        if USE_AWS:
            movies_table.put_item(Item={
                'movie_id': str(uuid.uuid4()),
                'title': request.form['title'],
                'genre': 'General',
                'theaters': ['Main Hall'],
                'time': '8:00 PM',
                'price': '12.00'
            })
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)