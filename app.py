import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
import psycopg2.extras
from supabase import create_client, Client
from dotenv import load_dotenv
from utils import email_utils

load_dotenv()  # Load environment variables from .env if running locally

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")  # Replace in production

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session['username'] = user['username']
            session['user_role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT o.id as owner_id, o.name, o.office_location, o.email,
               v.license_plate, v.vehicle_type
        FROM owners o
        LEFT JOIN vehicles v ON o.id = v.owner_id
    ''')
    data = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('dashboard.html', data=data, user_role=session.get('user_role'))

@app.route('/add_owner', methods=['GET', 'POST'])
def add_owner():
    if request.method == 'POST':
        name = request.form['name']
        office_location = request.form['office_location']
        email = request.form['email']
        contact_number = request.form['contact_number']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO owners (name, office_location, email, contact_number) VALUES (%s, %s, %s, %s)",
            (name, office_location, email, contact_number)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Owner added", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_owner.html')  # Show the form on GET

@app.route('/add_vehicle', methods=['GET', 'POST'])
def add_vehicle():
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        license_plate = request.form['license_plate']
        vehicle_type = request.form['vehicle_type']
        owner_id = request.form['owner_id']

        cur.execute(
            "INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (%s, %s, %s)",
            (license_plate, vehicle_type, owner_id)
        )
        conn.commit()
        flash('Vehicle added successfully', 'success')
        return redirect(url_for('dashboard'))

    # GET method: fetch owners to populate the dropdown
    cur.execute("SELECT id, name FROM owners ORDER BY name ASC")
    owners = [dict(id=row['id'], name=row['name']) for row in cur.fetchall()]
    cur.close()
    conn.close()

    return render_template('add_vehicle.html', owners=owners)


@app.route('/delete_vehicle/<license_plate>', methods=['POST'])
def delete_vehicle(license_plate):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM vehicles WHERE license_plate = %s", (license_plate,))
    conn.commit()
    cur.close()
    conn.close()
    flash(f"Deleted vehicle {license_plate}", "warning")
    return redirect(url_for('dashboard'))

from psycopg2.extras import RealDictCursor

@app.route('/vehicle/notify/<license_plate>', methods=['POST'])
def notify_owner(license_plate):
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('view_data'))

    with get_db_connection() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT o.name, o.email, o.office_location, v.license_plate 
            FROM vehicles v
            JOIN owners o ON v.owner_id = o.id
            WHERE v.license_plate = %s
        ''', (license_plate,))
        vehicle = cur.fetchone()
        cur.close()

    if not vehicle:
        flash("Vehicle not found.", "warning")
        return redirect(url_for('view_data'))

    if not vehicle['email']:
        flash("Owner email not available.", "warning")
        return redirect(url_for('view_data'))

    success, msg = send_email_notification(
        receiver_email=vehicle['email'],
        owner_name=vehicle['name'],
        license_plate=vehicle['license_plate'],
        location=vehicle['office_location']
    )

    flash(
        f"Notification sent to {vehicle['name']}." if success else f"Failed to send: {msg}",
        "success" if success else "danger"
    )
    return redirect(url_for('view_data'))

@app.route('/import-csv', methods=['GET', 'POST'])
def import_csv():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename.endswith('.csv'):
            # TODO: implement CSV parsing and DB insertion logic
            flash("CSV uploaded successfully", "success")
        else:
            flash("Invalid file format. Please upload a .csv file.", "danger")
    return render_template('import_csv.html')

@app.route('/view-data')
def view_data():
    search_plate = request.args.get('search_plate', '').strip()
    conn = get_db_connection()
    cur = conn.cursor()

    if search_plate:
        cur.execute("""
            SELECT o.name, o.office_location, o.email, o.contact_number,
                   v.license_plate, v.vehicle_type
            FROM owners o
            LEFT JOIN vehicles v ON o.id = v.owner_id
            WHERE v.license_plate ILIKE %s
        """, (f"%{search_plate}%",))
    else:
        cur.execute("""
            SELECT o.name, o.office_location, o.email, o.contact_number,
                   v.license_plate, v.vehicle_type
            FROM owners o
            LEFT JOIN vehicles v ON o.id = v.owner_id
        """)

    data = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('view_data.html', data=data, user_role=session.get('user_role'), search_plate=search_plate)

if __name__ == '__main__':
    app.run(debug=True)
