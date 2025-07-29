import os
from flask import Flask, render_template, request, redirect, url_for, flash
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key")

# Supabase credentials from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    owners_data = supabase.table("owners").select("*").execute()
    vehicles_data = supabase.table("vehicles").select("*").execute()

    owners = owners_data.data if owners_data and owners_data.data else []
    vehicles = vehicles_data.data if vehicles_data and vehicles_data.data else []

    return render_template('dashboard.html', owners=owners, vehicles=vehicles)

@app.route('/add_owner', methods=['POST'])
def add_owner():
    name = request.form['name']
    office_location = request.form['office_location']
    email = request.form['email']

    result = supabase.table("owners").insert({
        "name": name,
        "office_location": office_location,
        "email": email
    }).execute()

    if hasattr(result, "error") and result.error:
        flash("Failed to add owner", "danger")
    else:
        flash("Owner added successfully", "success")

    return redirect(url_for('dashboard'))

@app.route('/add_vehicle', methods=['POST'])
def add_vehicle():
    license_plate = request.form['license_plate']
    vehicle_type = request.form['vehicle_type']
    owner_id = request.form['owner_id']

    result = supabase.table("vehicles").insert({
        "license_plate": license_plate,
        "vehicle_type": vehicle_type,
        "owner_id": owner_id
    }).execute()

    if hasattr(result, "error") and result.error:
        flash("Failed to add vehicle", "danger")
    else:
        flash("Vehicle added successfully", "success")

    return redirect(url_for('dashboard'))

@app.route('/delete_vehicle/<license_plate>', methods=['POST'])
def delete_vehicle(license_plate):
    result = supabase.table("vehicles").delete().eq("license_plate", license_plate).execute()
    if hasattr(result, "error") and result.error:
        flash("Failed to delete vehicle", "danger")
    else:
        flash(f"Deleted vehicle {license_plate}", "warning")

    return redirect(url_for('dashboard'))

@app.route('/notify_owner/<license_plate>', methods=['POST'])
def notify_owner(license_plate):
    flash(f"Notification sent for vehicle {license_plate}", "info")
    return redirect(url_for('dashboard'))

@app.route('/view-data')
def view_data():
    result = supabase.table("vehicles").select("*").execute()
    vehicles = result.data if result and result.data else []
    return render_template('view_data.html', vehicles=vehicles)

if __name__ == '__main__':
    app.run(debug=True)
