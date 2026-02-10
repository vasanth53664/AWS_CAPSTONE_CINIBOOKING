import uuid
import datetime
import boto3
import qrcode
from io import BytesIO
from base64 import b64encode
from flask import Flask, render_template, session, redirect, url_for, request
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'aws_ultimate_key'

# --- 1. AWS CONFIG ---
REGION = 'us-east-1' # or 'ap-south-1'
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('Cinibooker_Bookings')

bookings_table = dynamodb.Table('Cinibooker_Bookings')
users_table = dynamodb.Table('Cinibooker_Users')
movies_table = dynamodb.Table('Cinibooker_Movies')

# --- 2. AWS HELPERS ---
def get_sns_topic_arn():
    try:
        r = sns_client.list_topics()
        return r['Topics'][0]['TopicArn'] if r['Topics'] else None
    except: return None

def send_notification(subj, msg):
    try:
        arn = get_sns_topic_arn()
        if arn: sns_client.publish(TopicArn=arn, Subject=subj, Message=msg)
    except: pass

def get_analytics():
    try:
        items = bookings_table.scan().get('Items', [])
        rev = sum(float(b['price']) for b in items)
        return {'revenue': f"₹{rev:,.2f}", 'tickets': len(items)}
    except: return {'revenue': 0, 'tickets': 0}

def get_occupied_seats(title):
    try:
        items = bookings_table.scan().get('Items', [])
        occupied = []
        for b in items:
            if b.get('movie_title') == title:
                occupied.extend([s.strip() for s in b['seats'].split(',')])
        return occupied
    except: return []

def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    return b64encode(buffered.getvalue()).decode("utf-8")

def is_valid_luhn(n):
    n = n.replace(" ", "")
    if not n.isdigit(): return False
    t=0; r=n[::-1]
    for i,d in enumerate(r):
        x=int(d); 
        if i%2==1: x*=2
        if x>9: x-=9
        t+=x
    return t%10==0

# --- 3. ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    # Fetch & Search
    movies = movies_table.scan().get('Items', [])
    query = request.args.get('q')
    if query:
        q = query.lower()
        movies = [m for m in movies if q in m.get('title','').lower() or q in m.get('genre','').lower()]
    
    stats = get_analytics() if session.get('is_admin') else None
    return render_template('dashboard.html', movies=movies, is_admin=session.get('is_admin'), analytics=stats)

@app.route('/book/<movie_id>')
def book(movie_id):
    if 'username' not in session: return redirect(url_for('login'))
    movies = movies_table.scan().get('Items', [])
    movie = next((m for m in movies if str(m['movie_id']) == str(movie_id)), None)
    return render_template('booking.html', movie=movie, occupied_seats=get_occupied_seats(movie.get('title')))

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        d = request.form
        if d['payment_method'] == 'card' and not is_valid_luhn(d['card_number']):
            return render_template('payment.html', error="Invalid Card", **d)
        
        bid = str(uuid.uuid4())[:8]
        bookings_table.put_item(Item={
            'booking_id': bid, 'username': session['username'],
            'movie_title': d['movie_title'], 'theater': d['theater'],
            'seats': ", ".join(d.getlist('seats')), 'price': str(d['total_price']),
            'date': datetime.datetime.now().strftime("%Y-%m-%d")
        })
        send_notification("Booking Confirmed", f"Movie: {d['movie_title']}\nID: {bid}")
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
    items = bookings_table.scan().get('Items', [])
    user_bookings = [b for b in items if b['username'] == session['username']]
    for b in user_bookings:
        b['qr_code'] = generate_qr(f"ID:{b['booking_id']}")
    return render_template('my_tickets.html', bookings=user_bookings)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        u = request.form['username']
        try:
            if 'Item' in users_table.get_item(Key={'username': u}): return render_template('signup.html', error="Exists")
            users_table.put_item(Item={
                'username': u, 'password': generate_password_hash(request.form['password']),
                'mobile': request.form['mobile'], 'email': request.form['email']
            })
            send_notification("Welcome", f"Welcome {u}!")
            return redirect(url_for('login'))
        except: return "DB Error"
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        if u == 'admin' and p == 'password123':
            session['username'], session['is_admin'] = u, True
            return redirect(url_for('dashboard'))
        try:
            r = users_table.get_item(Key={'username': u})
            if 'Item' in r and check_password_hash(r['Item']['password'], p):
                session['username'], session['is_admin'] = u, False
                return redirect(url_for('dashboard'))
        except: pass
        return render_template('login.html', error="Invalid Login")
    return render_template('login.html')

@app.route('/admin/add', methods=['GET', 'POST'])
def add_movie():
    if not session.get('is_admin'): return "Denied", 403
    if request.method == 'POST':
        movies_table.put_item(Item={
            'movie_id': str(uuid.uuid4()), 'title': request.form['title'],
            'genre': request.form['genre'], 'theaters': request.form['theaters'].split(','),
            'time': request.form['time'], 'price': str(request.form['price'])
        })
        return redirect(url_for('dashboard'))
    return render_template('admin_add.html')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)