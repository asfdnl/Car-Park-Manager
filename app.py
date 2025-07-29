import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from utils.email_utils import send_email_notification  # Must exist

# --- Load env ---
load_dotenv()

# --- Flask Config ---
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-secret')
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- PostgreSQL (Supabase) DB connection ---
def get_db_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor
    )

# --- Auth Decorator ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_role' in session else 'login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
            user = cur.fetchone()

        if user:
            session['username'] = username
            session['user_role'] = user['role']
            flash(f"Welcome, {username}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user_role=session['user_role'])


# --- Add Owner ---
@app.route('/owners/add', methods=['GET', 'POST'])
@login_required
def add_owner():
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        office = request.form['office_location'].strip()
        email = request.form['email'].strip()
        contact = request.form['contact_number'].strip()

        if not name:
            flash("Owner name is required.", "warning")
            return render_template('add_owner.html')

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO owners (name, office_location, email, contact_number) VALUES (%s, %s, %s, %s)",
                    (name, office, email, contact)
                )
                conn.commit()
            flash("Owner added successfully.", "success")
            return redirect(url_for('view_data'))
        except Exception as e:
            flash(f"Error adding owner: {e}", "danger")

    return render_template('add_owner.html')


# --- Add Vehicle ---
@app.route('/vehicles/add', methods=['GET', 'POST'])
@login_required
def add_vehicle():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM owners ORDER BY name")
        owners = cur.fetchall()

    if request.method == 'POST':
        license_plate = request.form['license_plate'].strip().upper()
        vehicle_type = request.form['vehicle_type']
        owner_id = request.form.get('owner_id')

        if not (license_plate and vehicle_type and owner_id):
            flash("All fields are required.", "warning")
            return render_template('add_vehicle.html', owners=owners)

        try:
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (%s, %s, %s)",
                    (license_plate, vehicle_type, int(owner_id))
                )
                conn.commit()
            flash("Vehicle added successfully.", "success")
            return redirect(url_for('view_data'))
        except Exception as e:
            flash(f"Error adding vehicle: {e}", "danger")

    return render_template('add_vehicle.html', owners=owners)


# --- View Data ---
@app.route('/view', methods=['GET'])
@login_required
def view_data():
    search_plate = request.args.get('search_plate', '').strip().upper()
    query = '''
        SELECT o.id as owner_id, o.name, o.office_location, o.email, o.contact_number,
               v.license_plate, v.vehicle_type
        FROM owners o
        LEFT JOIN vehicles v ON o.id = v.owner_id
    '''
    params = []
    if search_plate:
        query += " WHERE UPPER(v.license_plate) LIKE %s"
        params.append(f"%{search_plate}%")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        data = cur.fetchall()

    return render_template('view_data.html', data=data, user_role=session['user_role'], search_plate=search_plate)


# --- Delete Vehicle ---
@app.route('/vehicle/delete/<license_plate>', methods=['POST'])
@login_required
def delete_vehicle(license_plate):
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('view_data'))

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT owner_id FROM vehicles WHERE license_plate = %s", (license_plate,))
        vehicle = cur.fetchone()
        if not vehicle:
            flash("Vehicle not found.", "warning")
            return redirect(url_for('view_data'))

        owner_id = vehicle['owner_id']
        cur.execute("DELETE FROM vehicles WHERE license_plate = %s", (license_plate,))
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM vehicles WHERE owner_id = %s", (owner_id,))
        if cur.fetchone()['count'] == 0:
            cur.execute("DELETE FROM owners WHERE id = %s", (owner_id,))
            conn.commit()
            flash(f"Vehicle deleted and owner {owner_id} removed.", "info")
        else:
            flash("Vehicle deleted.", "info")

    return redirect(url_for('view_data'))


# --- Notify Owner ---
@app.route('/vehicle/notify/<license_plate>', methods=['POST'])
@login_required
def notify_owner(license_plate):
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('view_data'))

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('''
            SELECT o.name, o.email, o.office_location, v.license_plate 
            FROM vehicles v
            JOIN owners o ON v.owner_id = o.id
            WHERE v.license_plate = %s
        ''', (license_plate,))
        vehicle = cur.fetchone()

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

    flash(f"Notification sent to {vehicle['name']}." if success else f"Failed to send: {msg}",
          "success" if success else "danger")
    return redirect(url_for('view_data'))


# --- CSV Import ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash("No file selected.", "warning")
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash("Only CSV files are allowed.", "warning")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        import csv
        log = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            with open(filepath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    try:
                        name = row['owner_name'].strip()
                        office = row['office_location'].strip()
                        email = row['email'].strip()
                        contact = row['contact_number'].strip()
                        plate = row['license_plate'].strip().upper()
                        vtype = row['vehicle_type'].strip().capitalize()

                        cur.execute("SELECT id FROM owners WHERE name = %s AND email = %s", (name, email))
                        owner = cur.fetchone()
                        owner_id = owner['id'] if owner else None

                        if not owner_id:
                            cur.execute(
                                "INSERT INTO owners (name, office_location, email, contact_number) VALUES (%s, %s, %s, %s)",
                                (name, office, email, contact)
                            )
                            conn.commit()
                            cur.execute("SELECT id FROM owners WHERE name = %s AND email = %s", (name, email))
                            owner_id = cur.fetchone()['id']

                        cur.execute(
                            "INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (%s, %s, %s)",
                            (plate, vtype, owner_id)
                        )
                        conn.commit()
                        log.append(f"Imported vehicle {plate} for owner {name}.")
                    except Exception as e:
                        log.append(f"Failed to import row {row}: {e}")

        flash("CSV Import complete. See log.", "info")
        return render_template('import_csv.html', log=log)

    return render_template('import_csv.html')


if __name__ == '__main__':
    app.run(debug=True)
