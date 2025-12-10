from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Замените на реальный секретный ключ
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sound.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    avatar = db.Column(db.String(150))  # Путь к аватарке
    display_name = db.Column(db.String(150))
    bio = db.Column(db.Text)
    last_seen = db.Column(db.DateTime, default=db.func.now())
    private_profile = db.Column(db.Boolean, default=False)  # show offline status

    # Отношения
    sent_messages = db.relationship('Message', foreign_keys='Message.user_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy=True)
    friendships = db.relationship('Friendship', foreign_keys='Friendship.user_id', backref='user', lazy=True)
    reverse_friendships = db.relationship('Friendship', foreign_keys='Friendship.friend_id', backref='friend', lazy=True)
    chat_rooms = db.relationship('ChatRoomMember', backref='user', lazy=True)

class Friendship(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(50), default='accepted')  # pending, accepted, etc.

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ChatRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.now())

    members = db.relationship('ChatRoomMember', backref='room', lazy=True)

class ChatRoomMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('chat_room.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = db.func.now()
        db.session.commit()

# Маршруты
@app.route('/')
@login_required
def index():
    theme = session.get('theme', 'dark')
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('index.html', users=users, theme=theme)

@app.route('/registration', methods=['GET', 'POST'])
def registration():
    app.jinja_env.cache = {}  # Очистка кэша Jinja
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        display_name = request.form.get('display_name')

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким username уже существует', 'error')
            return redirect(url_for('registration'))

        avatar_file = request.files.get('avatar')
        avatar_filename = None
        if avatar_file and avatar_file.filename:
            avatar_filename = avatar_file.filename
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

        user = User()
        user.username = username
        user.password = password
        user.display_name = display_name
        user.avatar = avatar_filename
        db.session.add(user)
        db.session.commit()
        # Send welcome message
        bot = User.query.filter_by(username='sound_bot').first()
        if bot:
            message = Message()
            message.user_id = bot.id
            message.recipient_id = user.id
            message.content = 'Добро пожаловать в Sound! Я ваш помощник бот. Приглашайте друзей и общайтесь!'
            db.session.add(message)
            db.session.commit()
        flash('Регистрация успешна', 'success')
        return redirect(url_for('login'))

    return render_template('registration.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('profile', user_id=user.id))
        flash('Неверные учетные данные', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/profile/<int:user_id>', methods=['GET', 'POST'])
@login_required
def profile(user_id):
    theme = session.get('theme', 'dark')
    user = User.query.get_or_404(user_id)
    is_owner = (user.id == current_user.id)
    if request.method == 'POST' and is_owner:
        current_user.display_name = request.form['display_name']
        current_user.bio = request.form['bio']
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_file.filename))
            current_user.avatar = avatar_file.filename
        db.session.commit()
        flash('Профиль обновлен', 'success')
        return redirect(url_for('profile', user_id=user_id))
    return render_template('profile.html', user=user, is_owner=is_owner, theme=theme)

@app.route('/chat/<int:recipient_id>', methods=['GET', 'POST'])
@login_required
def chat(recipient_id):
    theme = session.get('theme', 'dark')
    recipient = User.query.get_or_404(recipient_id)
    if request.method == 'POST':
        content = request.form['content']
        message = Message()
        message.content = content
        message.user_id = current_user.id
        message.recipient_id = recipient_id
        db.session.add(message)
        db.session.commit()
        return redirect(url_for('chat', recipient_id=recipient_id))
    messages = Message.query.filter(
        ((Message.user_id == current_user.id) & (Message.recipient_id == recipient_id)) |
        ((Message.user_id == recipient_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.timestamp).all()
    return render_template('chat.html', recipient=recipient, messages=messages, theme=theme)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        theme = request.form['theme']
        session['theme'] = theme
        flash('Настройки сохранены', 'success')
        return redirect(url_for('settings'))
    theme = session.get('theme', 'dark')
    return render_template('settings.html', theme=theme)

@app.route('/friends', methods=['GET', 'POST'])
@login_required
def friends():
    theme = session.get('theme', 'dark')
    if request.method == 'POST':
        search_type = request.form.get('search_type')
        query = request.form.get('query')
        user = None
        if search_type == 'username' and query:
            user = User.query.filter_by(username=query).first()
        elif search_type == 'id' and query:
            try:
                user_id = int(query)
                user = User.query.get(user_id)
            except ValueError:
                user = None

        if user and user.id != current_user.id:
            # Check if friendship exists
            existing = Friendship.query.filter(
                ((Friendship.user_id == current_user.id) & (Friendship.friend_id == user.id)) |
                ((Friendship.friend_id == current_user.id) & (Friendship.user_id == user.id))
            ).first()
            if not existing:
                friendship = Friendship()
                friendship.user_id = current_user.id
                friendship.friend_id = user.id
                db.session.add(friendship)
                db.session.commit()
                flash('Друг добавлен!', 'success')
            else:
                flash('Уже друзья!', 'info')
        else:
            flash('Пользователь не найден!', 'error')
        return redirect(url_for('friends'))

    # Get my friends
    friends = []
    my_friendships = Friendship.query.filter(
        (Friendship.user_id == current_user.id) | (Friendship.friend_id == current_user.id)
    ).all()
    for f in my_friendships:
        friend_id = f.friend_id if f.friend_id != current_user.id else f.user_id
        friend = User.query.get(friend_id)
        if friend:
            friends.append(friend)

    return render_template('friends.html', friends=friends, theme=theme)

@app.route('/create_chat', methods=['GET', 'POST'])
@login_required
def create_chat():
    theme = session.get('theme', 'dark')
    if request.method == 'POST':
        chat_type = request.form['chat_type']  # 'chat' or 'group'
        name = request.form.get('name')
        description = request.form.get('description')
        is_public = request.form.get('is_public') == 'on'
        invited_users = request.form.getlist('invited_users')  # list of usernames or ids

        room = ChatRoom()
        room.name = name or f'Чат {current_user.username}'
        room.description = description
        room.creator_id = current_user.id
        room.is_public = is_public
        db.session.add(room)
        db.session.commit()

        # Add creator
        member = ChatRoomMember()
        member.room_id = room.id
        member.user_id = current_user.id
        db.session.add(member)

        # Add invited users if group
        if chat_type == 'group':
            for user_ident in invited_users:
                if user_ident.isdigit():
                    user = User.query.get(int(user_ident))
                else:
                    user = User.query.filter_by(username=user_ident).first()
                if user and user.id != current_user.id:
                    member = ChatRoomMember()
                    member.room_id = room.id
                    member.user_id = user.id
                    db.session.add(member)

        db.session.commit()
        flash('Чат создан!', 'success')
        return redirect(url_for('room', room_id=room.id))

    friends = []
    my_friendships = Friendship.query.filter(
        (Friendship.user_id == current_user.id) | (Friendship.friend_id == current_user.id)
    ).all()
    for f in my_friendships:
        friend_id = f.friend_id if f.friend_id != current_user.id else f.user_id
        friend = User.query.get(friend_id)
        if friend:
            friends.append(friend)

    return render_template('create_chat.html', friends=friends, theme=theme)

@app.route('/chat_room/<int:room_id>')
@login_required
def room(room_id):
    theme = session.get('theme', 'dark')
    room = ChatRoom.query.get_or_404(room_id)
    # Check if user is member
    member = ChatRoomMember.query.filter_by(room_id=room_id, user_id=current_user.id).first()
    if not member and not room.is_public:
        flash('Нет доступа', 'error')
        return redirect(url_for('index'))
    return render_template('room.html', room=room, theme=theme)

if __name__ == '__main__':
    with app.app_context():
        # Drop all tables to recreate if changed
        db.drop_all()
        db.create_all()
        # Create welcome system user if needed
        system_user = User.query.filter_by(username='sound_bot').first()
        if not system_user:
            system_user = User()
            system_user.username = 'sound_bot'
            system_user.password = 'hashed'
            system_user.display_name = 'Саунд Бот'
            system_user.avatar = 'sound_bot.png'
            db.session.add(system_user)
            db.session.commit()
        # Add welcome message for new users
    app.run(debug=True)
