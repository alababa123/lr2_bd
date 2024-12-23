import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
import telebot
from telebot.types import Message
from matplotlib.figure import Figure
import io
import base64
from threading import Thread

# Flask app setup
app = Flask(__name__)
app.secret_key = 'secret'

# Database setup
DATABASE = 'bot_database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    conn = get_db_connection()
    with conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
                            id INTEGER PRIMARY KEY,
                            username TEXT,
                            password TEXT,
                            role TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS responses (
                            id INTEGER PRIMARY KEY,
                            trigger TEXT,
                            response TEXT
                        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER,
                            message TEXT,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                        )''')
    conn.close()

initialize_db()

# Telegram bot setup
BOT_TOKEN = '7690697807:AAGHcrbhzIIxy-YEU4oNhzSbzbymBHY7acQ'
bot = telebot.TeleBot(BOT_TOKEN)

# Authorization and roles
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        conn = get_db_connection()
        conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (username, password, role))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'role' not in session:
        return redirect(url_for('login'))

    role = session['role']
    conn = get_db_connection()
    responses = conn.execute('SELECT * FROM responses').fetchall()
    conn.close()

    if role in ['Руководитель', 'Управляющий']:
        return render_template('dashboard.html', responses=responses, show_add_button=True, show_stats=(role == 'Руководитель'))
    else:
        return "Access denied"



@app.route('/add_response', methods=['GET', 'POST'])
def add_response():
    if 'role' not in session or session['role'] not in ['Управляющий', 'Руководитель']:
        return redirect(url_for('login'))

    if request.method == 'POST':
        trigger = request.form['trigger']
        response = request.form['response']
        conn = get_db_connection()
        conn.execute('INSERT INTO responses (trigger, response) VALUES (?, ?)', (trigger, response))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    return render_template('add_response.html')


@app.route('/edit_response/<int:response_id>', methods=['GET', 'POST'])
def edit_response(response_id):
    if 'role' not in session or session['role'] not in ['Управляющий', 'Руководитель']:
        return redirect(url_for('login'))

    conn = get_db_connection()
    response = conn.execute('SELECT * FROM responses WHERE id = ?', (response_id,)).fetchone()

    if request.method == 'POST':
        new_response = request.form['response']
        conn.execute('UPDATE responses SET response = ? WHERE id = ?', (new_response, response_id))
        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))

    conn.close()
    return render_template('edit_response.html', response=response)

@app.route('/stats', methods=['GET', 'POST'])
def stats():
    if 'role' not in session or session['role'] != 'Руководитель':
        return redirect(url_for('login'))

    filters = {}
    query = "SELECT * FROM messages WHERE 1=1"
    
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        telegram_id = request.form.get('telegram_id')
        
        if start_date:
            query += " AND timestamp >= :start_date"
            filters['start_date'] = start_date
        if end_date:
            query += " AND timestamp <= :end_date"
            filters['end_date'] = end_date
        if telegram_id:
            query += " AND user_id = :telegram_id"
            filters['telegram_id'] = telegram_id

    conn = get_db_connection()
    messages = conn.execute(query, filters).fetchall()
    conn.close()

    # Generate statistics graph
    fig = Figure()
    ax = fig.subplots()
    timestamps = [row['timestamp'] for row in messages]
    ax.hist(timestamps, bins=10)
    ax.set_title("Messages Statistics")
    ax.set_xlabel("Time")
    ax.set_ylabel("Number of Messages")

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    buf.close()

    return render_template('stats.html', messages=messages, img_base64=img_base64)

# Telegram bot functions
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: Message):
    conn = get_db_connection()
    conn.execute('INSERT INTO messages (user_id, message) VALUES (?, ?)', (message.from_user.id, message.text))
    conn.commit()
    conn.close()
    bot.reply_to(message, "Welcome! How can I help you?")

@bot.message_handler(func=lambda m: True)
def handle_message(message: Message):
    conn = get_db_connection()
    response = conn.execute('SELECT response FROM responses WHERE trigger = ?', (message.text,)).fetchone()
    conn.execute('INSERT INTO messages (user_id, message) VALUES (?, ?)', (message.from_user.id, message.text))
    conn.commit()
    conn.close()

    if response:
        bot.reply_to(message, response['response'])
    else:
        bot.reply_to(message, "Sorry, I don't understand that.")


if __name__ == '__main__':
    # Запуск бота в отдельном потоке


    # Запуск Flask приложения
    app.run(debug=True)
