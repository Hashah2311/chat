import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, flash
from functools import wraps
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import uuid
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'a_very_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

IST = pytz.timezone('Asia/Kolkata')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # type: ignore

# --- Database Models ---
user_rooms = db.Table('user_rooms',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('room_name', db.String(100), db.ForeignKey('room.name'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    rooms = db.relationship('Room', secondary=user_rooms, lazy='subquery',
                            backref=db.backref('users', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Room(db.Model):
    name = db.Column(db.String(100), primary_key=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_name = db.Column(db.String(100), db.ForeignKey('room.name'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_file = db.Column(db.Boolean, default=False)
    filename = db.Column(db.String(200), nullable=True)

    user = db.relationship('User', backref=db.backref('messages', lazy=True))
    room = db.relationship('Room', backref=db.backref('messages', lazy=True))

# --- Login Manager ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create uploads directory if it doesn't exist
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            # Make the first registered user an admin
            is_admin = User.query.count() == 0
            new_user = User(username=username, is_admin=is_admin) # type: ignore
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            if is_admin:
                flash('Registration successful! You are now an admin. Please log in.')
            else:
                flash('Registration successful! Please log in.')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Serve static files from the 'uploads' directory
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOADS_DIR, filename)

@app.route('/')
@login_required
def index():
    return render_template('index.html', rooms=[room.name for room in current_user.rooms], is_admin=current_user.is_admin)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    room_name = request.form.get('room', 'general')
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file:
        original_filename = secure_filename(file.filename or "")
        unique_filename = str(uuid.uuid4()) + "_" + original_filename
        file_path = os.path.join(UPLOADS_DIR, unique_filename)
        file.save(file_path)
        
        file_url = f'/uploads/{unique_filename}'
        
        new_message = Message(
            room_name=room_name, # type: ignore
            user_id=current_user.id, # type: ignore
            username=current_user.username, # type: ignore
            content=file_url, # type: ignore
            is_file=True, # type: ignore
            filename=original_filename # Store the original filename for display # type: ignore
        )
        db.session.add(new_message)
        db.session.commit()

        # FIX: First, localize the naive UTC time, then convert to IST
        timestamp_ist = pytz.utc.localize(new_message.timestamp).astimezone(IST)

        socketio.emit('receive_message', {
            'user': current_user.username,
            'message': file_url,
            'is_file': True,
            'filename': original_filename,
            'url': file_url,
            'timestamp': timestamp_ist.isoformat() # Send the correct IST timestamp
        }, to=room_name)
        
        return jsonify({'success': True, 'url': file_url})
    return jsonify({'error': 'File upload failed'}), 500

@socketio.on('join')
def on_join(data):
    room_name = data['room']
    join_room(room_name)

    room = Room.query.get(room_name)
    if not room:
        room = Room(name=room_name) # type: ignore
        db.session.add(room)
    
    if room not in current_user.rooms:
        current_user.rooms.append(room)
        db.session.commit()

    # Fetch history and send as a single batch
    history_messages = Message.query.filter_by(room_name=room_name).order_by(Message.timestamp).all()
    history_batch = [{
        'user': msg.username,
        'message': msg.content,
        'is_file': msg.is_file,
        'filename': msg.filename,
        'url': msg.content if msg.is_file else None,
        # FIX: First, localize the naive UTC time, then convert to IST
        'timestamp': pytz.utc.localize(msg.timestamp).astimezone(IST).isoformat()
    } for msg in history_messages]
    
    emit('load_history', history_batch)

@socketio.on('send_message')
def handle_send_message(data):
    room_name = data['room']
    message_content = data['message']
    
    new_message = Message(
        room_name=room_name, # type: ignore
        user_id=current_user.id, # type: ignore
        username=current_user.username, # type: ignore
        content=message_content # type: ignore
    )
    db.session.add(new_message)
    db.session.commit()

    # FIX: First, localize the naive UTC time, then convert to IST
    timestamp_ist = pytz.utc.localize(new_message.timestamp).astimezone(IST)

    emit('receive_message', {
        'user': current_user.username,
        'message': message_content,
        'is_file': False,
        'timestamp': timestamp_ist.isoformat() # Send the correct IST timestamp
    }, to=room_name)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("You don't have permission to access this page.")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@login_required
@admin_required
def admin():
    users = User.query.all()
    rooms = Room.query.all()
    files = []
    if os.path.exists(UPLOADS_DIR):
        for filename in os.listdir(UPLOADS_DIR):
            files.append(filename)
    return render_template('admin.html', users=users, rooms=rooms, files=files)

@app.route('/admin/login_as/<int:user_id>')
@login_required
@admin_required
def login_as(user_id):
    user = User.query.get(user_id)
    if user:
        login_user(user)
        return redirect(url_for('index'))
    else:
        flash('User not found.')
        return redirect(url_for('admin'))

@app.route('/admin/room/<room_name>/clear', methods=['POST'])
@login_required
@admin_required
def admin_clear_room(room_name):
    Message.query.filter_by(room_name=room_name).delete()
    db.session.commit()
    flash(f'Chat history for room "{room_name}" has been cleared.')
    return redirect(url_for('admin'))

@app.route('/admin/room/<room_name>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_room(room_name):
    room = Room.query.get(room_name)
    if room:
        # Delete file messages from the filesystem
        messages = Message.query.filter_by(room_name=room_name).all()
        for message in messages:
            if message.is_file:
                try:
                    file_path = os.path.join(UPLOADS_DIR, message.content.split('/')[-1])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    flash(f'Error deleting file for message {message.id}: {e}')
        
        # Delete messages in the room
        Message.query.filter_by(room_name=room_name).delete()
        
        # Delete room from user associations
        for user in room.users:
            user.rooms.remove(room)
            
        # Delete the room itself
        db.session.delete(room)
        db.session.commit()
        flash(f'Room "{room_name}" has been deleted.')
    else:
        flash(f'Room "{room_name}" not found.')
    return redirect(url_for('admin'))

@app.route('/admin/file/<filename>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_file(filename):
    try:
        # Delete the file from the filesystem
        file_path = os.path.join(UPLOADS_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete the message from the database
        file_url = f'/uploads/{filename}'
        Message.query.filter_by(content=file_url).delete()
        db.session.commit()
        
        flash(f'File "{filename}" has been deleted.')
    except Exception as e:
        flash(f'Error deleting file "{filename}": {e}')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
