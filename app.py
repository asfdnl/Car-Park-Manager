import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
import psycopg2.extras

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

@app.route('/add_owner', methods=['POST'])
def add_owner():
    name = request.form['name']
    office_location = request.form['office_location']
    email = request.form['email']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO owners (name, office_location, email) VALUES (%s, %s, %s)", 
                (name, office_location, email))
    conn.commit()
    cur.close()
    conn.close()
    flash("Owner added", "success")
    return redirect(url_for('dashboard'))

@app.route('/add_vehicle', methods=['POST'])
def add_vehicle():
    license_plate = request.form['license_plate']
    vehicle_type = request.form['vehicle_type']
    owner_id = request.form['owner_id']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (%s, %s, %s)", 
                (license_plate, vehicle_type, owner_id))
    conn.commit()
    cur.close()
    conn.close()
    flash("Vehicle added", "success")
    return redirect(url_for('dashboard'))

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

@app.route('/notify_owner/<license_plate>', methods=['POST'])
def notify_owner(license_plate):
    # Placeholder for actual notification logic (email, etc.)
    flash(f"Notification sent for vehicle {license_plate}", "info")
    return redirect(url_for('dashboard'))

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
    # Replace with actual logic to fetch vehicle and owner data
    data = supabase.table('vehicles').select('*').execute().data
    return render_template('view_data.html', data=data)


if __name__ == '__main__':
    app.run(debug=True)
