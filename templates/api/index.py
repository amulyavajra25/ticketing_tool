import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session

DB_PATH = '/tmp/database.db' if os.environ.get('VERCEL') else 'database.db'

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = 'ticketing_system_secret_key_vercel_safe'

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                category TEXT,
                priority TEXT,
                status TEXT,
                raised_by TEXT,
                assigned_employee TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                sender TEXT,
                role TEXT,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            )
        ''')
        
        demo_users = [
            ('Client One', '1234', 'CLIENT'),
            ('Amulya', '1234', 'EMPLOYEE'),
            ('Admin', '1234', 'ADMINISTRATOR')
        ]
        for user, pwd, role in demo_users:
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', (user, pwd, role))
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")

init_db()

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        session.clear()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'CLIENT').upper()
        
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            user = cursor.execute('SELECT * FROM users WHERE username = ? AND password = ? AND role = ?', 
                                  (username, password, role)).fetchone()
            conn.close()
            
            if user:
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('dashboard'))
            else:
                error = "Invalid username, password, or role selection."
        except Exception as e:
            error = f"Database error: {e}"
            
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'CLIENT').upper()
        
        if not username or not password:
            error = "Username and password are required."
        else:
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                               (username, password, role))
                conn.commit()
                conn.close()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = "Username already exists. Choose a different username or login."
            except Exception as e:
                error = f"Error: {e}"
    return render_template('register.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    username = session.get('username')
    role = session.get('role', 'CLIENT').upper()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    employee_rows = cursor.execute("SELECT username FROM users WHERE role = 'EMPLOYEE'").fetchall()
    employees = [emp['username'] for emp in employee_rows]
    if not employees:
        employees = ['Amulya', 'TestEmployee']
    
    if role == 'ADMINISTRATOR':
        tickets = cursor.execute('SELECT * FROM tickets').fetchall()
    elif role == 'EMPLOYEE':
        tickets = cursor.execute('''
            SELECT * FROM tickets 
            WHERE assigned_employee = ? OR assigned_employee = '' OR status = 'OPEN'
        ''', (username,)).fetchall()
    else:
        tickets = cursor.execute('SELECT * FROM tickets WHERE raised_by = ?', (username,)).fetchall()
        
    conn.close()
    return render_template('dashboard.html', tickets=tickets, username=username, role=role, employees=employees)

@app.route('/create_ticket', methods=['POST'])
def create_ticket():
    if 'username' not in session:
        return redirect(url_for('login'))
        
    title = request.form.get('title')
    category = request.form.get('category', 'Incident')
    priority = request.form.get('priority', 'MEDIUM')
    status = 'OPEN'
    raised_by = session.get('username')
    assigned_employee = '' 
    
    if title:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tickets (title, category, priority, status, raised_by, assigned_employee)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, category, priority, status, raised_by, assigned_employee))
        conn.commit()
        conn.close()
    return redirect(url_for('dashboard'))

@app.route('/assign_ticket/<int:ticket_id>', methods=['POST'])
def assign_ticket(ticket_id):
    if session.get('role') != 'ADMINISTRATOR':
        return redirect(url_for('dashboard'))
        
    assigned_employee = request.form.get('assigned_employee')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET assigned_employee = ?, status = 'ASSIGNED' WHERE id = ?", (assigned_employee, ticket_id))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
def ticket_detail(ticket_id):
    if 'username' not in session:
        return redirect(url_for('login'))
        
    username = session.get('username')
    role = session.get('role')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    ticket = cursor.execute('SELECT * FROM tickets WHERE id = ?', (ticket_id,)).fetchone()
    
    if not ticket:
        conn.close()
        return redirect(url_for('dashboard'))

    if role == 'EMPLOYEE' and ticket['assigned_employee'] != username:
        conn.close()
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        message = request.form.get('message')
        new_status = request.form.get('status')
        
        if new_status in ['OPEN', 'CLOSED'] and role not in ['ADMINISTRATOR', 'CLIENT']:
            new_status = None 

        if message:
            cursor.execute('INSERT INTO ticket_messages (ticket_id, sender, role, message) VALUES (?, ?, ?, ?)', (ticket_id, username, role, message))
        if new_status:
            cursor.execute('UPDATE tickets SET status = ? WHERE id = ?', (new_status, ticket_id))
            
        conn.commit()
        return redirect(url_for('ticket_detail', ticket_id=ticket_id))

    messages = cursor.execute('SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY timestamp ASC', (ticket_id,)).fetchall()
    conn.close()

    return render_template('ticket_detail.html', ticket=ticket, messages=messages, username=username, role=role)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)