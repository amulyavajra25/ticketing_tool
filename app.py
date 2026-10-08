import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, session, url_for

app = Flask(__name__)
app.secret_key = 'ticketing_system_secret_key_123'

DB_PATH = '/tmp/ticketing.db' if os.environ.get('VERCEL') or os.path.exists('/tmp') else 'ticketing.db'

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS tickets")
    cursor.execute("DROP TABLE IF EXISTS users")

    cursor.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            custom_id TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('ADMIN', 'EMPLOYEE', 'CLIENT')) NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')) NOT NULL,
            status TEXT CHECK(status IN ('OPEN', 'ASSIGNED', 'WORK_IN_PROGRESS', 'RESOLVED', 'CLOSED')) DEFAULT 'OPEN',
            created_by INTEGER NOT NULL,
            assigned_to INTEGER,
            FOREIGN KEY (created_by) REFERENCES users(user_id),
            FOREIGN KEY (assigned_to) REFERENCES users(user_id)
        )
    ''')

    demo_users = [
        ('ADM-1001', 'Mani Admin', 'mani@helpdesk.com', 'admin123', 'ADMIN'),
        ('EMP-2001', 'Amulya', 'amulya@helpdesk.com', 'emp123', 'EMPLOYEE'),
        ('EMP-2002', 'Taruni', 'taruni@helpdesk.com', 'emp123', 'EMPLOYEE'),
        ('CLT-1001', 'Client One', 'client1@gmail.com', 'client123', 'CLIENT'),
        ('CLT-1002', 'Client Two', 'client2@gmail.com', 'client123', 'CLIENT')
    ]

    cursor.executemany("INSERT INTO users (custom_id, username, email, password, role) VALUES (?, ?, ?, ?, ?)", demo_users)
    conn.commit()
    conn.close()

@app.before_request
def setup_database():
    if not os.path.exists(DB_PATH):
        init_db()

@app.route('/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['email'] = user['email']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            error = 'Invalid email or password.'

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'CLIENT').strip()

        prefix = 'CLT' if role == 'CLIENT' else ('EMP' if role == 'EMPLOYEE' else 'ADMIN')
        custom_id = f"{prefix}-{uuid.uuid4().hex[:4].upper()}"

        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (custom_id, username, email, password, role) VALUES (?, ?, ?, ?, ?)",
                (custom_id, username, email, password, role)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            error = f"Registration failed: {str(e)}"

    return render_template('register.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    role = session['role']
    user_id = session['user_id']

    query = '''
        SELECT t.*, 
               u.username AS raised_by, 
               COALESCE(e.username, 'Unassigned') AS assigned_employee
        FROM tickets t
        JOIN users u ON t.created_by = u.user_id
        LEFT JOIN users e ON t.assigned_to = e.user_id
    '''

    if role == 'ADMIN':
        cursor.execute(query)
    elif role == 'EMPLOYEE':
        cursor.execute(query + ' WHERE t.assigned_to = ? OR t.assigned_to IS NULL', (user_id,))
    else:  
        cursor.execute(query + ' WHERE t.created_by = ?', (user_id,))

    tickets = cursor.fetchall()
    
    cursor.execute("SELECT user_id, username FROM users WHERE role = 'EMPLOYEE'")
    employees = cursor.fetchall()
    conn.close()

    return render_template('dashboard.html', tickets=tickets, employees=employees)

@app.route('/create_ticket', methods=['POST'])
def create_ticket():
    if 'user_id' not in session or session['role'] != 'CLIENT':
        return redirect(url_for('dashboard'))

    title = request.form.get('title', '').strip()
    category = request.form.get('category', 'Incident').strip()
    priority = request.form.get('priority', 'MEDIUM').strip().upper()
    description = request.form.get('description', '').strip()

    if title:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tickets (title, description, category, priority, status, created_by)
            VALUES (?, ?, ?, ?, 'OPEN', ?)
        ''', (title, description, category, priority, session['user_id']))
        conn.commit()
        conn.close()

    return redirect(url_for('dashboard'))

@app.route('/assign_ticket/<int:ticket_id>', methods=['POST'])
def assign_ticket(ticket_id):
    if 'user_id' not in session or session['role'] != 'ADMIN':
        return redirect(url_for('login'))

    employee_id = request.form.get('employee_id')
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    if row and row['status'] == 'OPEN':
        cursor.execute("UPDATE tickets SET assigned_to = ?, status = 'ASSIGNED' WHERE ticket_id = ?", (employee_id, ticket_id))
    else:
        cursor.execute("UPDATE tickets SET assigned_to = ? WHERE ticket_id = ?", (employee_id, ticket_id))
        
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

@app.route('/update_status/<int:ticket_id>', methods=['POST'])
def update_status(ticket_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    status = request.form.get('status')
    role = session['role']

    if role == 'EMPLOYEE' and status in ('OPEN', 'CLOSED'):
        return redirect(url_for('dashboard'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = ? WHERE ticket_id = ?", (status, ticket_id))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)