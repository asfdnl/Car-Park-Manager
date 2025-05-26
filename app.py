import os
import sqlite3
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session
)
from werkzeug.utils import secure_filename
from utils.email_utils import send_email_notification  # Make sure this exists!

# --- Configuration ---
app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this to a strong random secret key!
DATABASE = 'vehicle_registry.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- DB helpers ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# --- Authentication decorator ---
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
    if 'user_role' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?',
            (username, password)
        ).fetchone()
        conn.close()

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

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO owners (name, office_location, email, contact_number) VALUES (?, ?, ?, ?)",
                (name, office, email, contact)
            )
            conn.commit()
            flash("Owner added successfully.", "success")
            return redirect(url_for('view_data'))
        except sqlite3.IntegrityError:
            flash("Error adding owner. Possibly duplicate entry.", "danger")
        finally:
            conn.close()

    return render_template('add_owner.html')


# --- Add Vehicle ---
@app.route('/vehicles/add', methods=['GET', 'POST'])
@login_required
def add_vehicle():
    conn = get_db_connection()
    owners = conn.execute("SELECT id, name FROM owners ORDER BY name").fetchall()

    if request.method == 'POST':
        license_plate = request.form['license_plate'].strip().upper()
        vehicle_type = request.form['vehicle_type']
        owner_id = request.form.get('owner_id')

        if not (license_plate and vehicle_type and owner_id):
            flash("All fields are required.", "warning")
            conn.close()
            return render_template('add_vehicle.html', owners=owners)

        try:
            conn.execute(
                "INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (?, ?, ?)",
                (license_plate, vehicle_type, int(owner_id))
            )
            conn.commit()
            flash("Vehicle added successfully.", "success")
            return redirect(url_for('view_data'))
        except sqlite3.IntegrityError:
            flash("Error adding vehicle. Possibly duplicate license plate.", "danger")
        finally:
            conn.close()

    return render_template('add_vehicle.html', owners=owners)


# --- View Data with search ---
@app.route('/view', methods=['GET'])
@login_required
def view_data():
    search_plate = request.args.get('search_plate', '').strip().upper()

    conn = get_db_connection()
    query = '''
        SELECT o.id as owner_id, o.name, o.office_location, o.email, o.contact_number,
               v.license_plate, v.vehicle_type
        FROM owners o
        LEFT JOIN vehicles v ON o.id = v.owner_id
    '''
    params = ()
    if search_plate:
        query += " WHERE UPPER(v.license_plate) LIKE ?"
        params = (f"%{search_plate}%",)

    data = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('view_data.html', data=data, user_role=session['user_role'], search_plate=search_plate)


# --- Delete Vehicle ---
@app.route('/vehicle/delete/<license_plate>', methods=['POST'])
@login_required
def delete_vehicle(license_plate):
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('view_data'))

    conn = get_db_connection()
    vehicle = conn.execute("SELECT * FROM vehicles WHERE license_plate = ?", (license_plate,)).fetchone()

    if not vehicle:
        flash("Vehicle not found.", "warning")
        conn.close()
        return redirect(url_for('view_data'))

    owner_id = vehicle['owner_id']

    conn.execute("DELETE FROM vehicles WHERE license_plate = ?", (license_plate,))
    conn.commit()

    # Check if owner has any vehicles left
    count = conn.execute("SELECT COUNT(*) FROM vehicles WHERE owner_id = ?", (owner_id,)).fetchone()[0]
    if count == 0:
        conn.execute("DELETE FROM owners WHERE id = ?", (owner_id,))
        conn.commit()
        flash(f"Vehicle {license_plate} deleted and owner ID {owner_id} removed (no vehicles left).", "info")
    else:
        flash(f"Vehicle {license_plate} deleted.", "info")

    conn.close()
    return redirect(url_for('view_data'))


# --- Send Notification Email ---
@app.route('/vehicle/notify/<license_plate>', methods=['POST'])
@login_required
def notify_owner(license_plate):
    if session['user_role'] != 'Admin':
        flash("Access denied: Admins only.", "danger")
        return redirect(url_for('view_data'))

    conn = get_db_connection()
    vehicle = conn.execute('''
        SELECT o.name, o.email, o.office_location, v.license_plate 
        FROM vehicles v
        JOIN owners o ON v.owner_id = o.id
        WHERE v.license_plate = ?
    ''', (license_plate,)).fetchone()
    conn.close()

    if not vehicle:
        flash("Vehicle not found.", "warning")
        return redirect(url_for('view_data'))

    if not vehicle['email']:
        flash("Owner email not available.", "warning")
        return redirect(url_for('view_data'))

    # Send email (imported from utils/email_utils.py)
    success, msg = send_email_notification(
        receiver_email=vehicle['email'],
        owner_name=vehicle['name'],
        license_plate=vehicle['license_plate'],
        location=vehicle['office_location']
    )

    if success:
        flash(f"Notification sent to {vehicle['name']} at {vehicle['email']}.", "success")
    else:
        flash(f"Failed to send email: {msg}", "danger")

    return redirect(url_for('view_data'))


# --- CSV Import helpers ---
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
        conn = get_db_connection()
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

                    existing = conn.execute(
                        "SELECT id FROM owners WHERE name=? AND email=?", (name, email)
                    ).fetchone()
                    if existing:
                        owner_id = existing['id']
                    else:
                        conn.execute(
                            "INSERT INTO owners (name, office_location, email, contact_number) VALUES (?, ?, ?, ?)",
                            (name, office, email, contact)
                        )
                        owner_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                    conn.execute(
                        "INSERT INTO vehicles (license_plate, vehicle_type, owner_id) VALUES (?, ?, ?)",
                        (plate, vtype, owner_id)
                    )
                    conn.commit()
                    log.append(f"Imported vehicle {plate} for owner {name}.")
                except Exception as e:
                    log.append(f"Failed to import row {row}: {e}")
        conn.close()
        flash("CSV Import completed. Check logs below.", "info")
        return render_template('import_csv.html', log=log)

    return render_template('import_csv.html')


if __name__ == '__main__':
    app.run(debug=True)
