from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io
from functools import wraps

# ==================== APP CONFIGURATION ====================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'rushi-salon-secret-key-2024'

# 🟢 FIXED: Updated MongoDB Atlas connection string format
app.config['MONGO_URI'] = 'mongodb+srv://anjanaadeashan2:admin@cluster0.pqnr3cd.mongodb.net/salon_db?retryWrites=true&w=majority'

# Initialize PyMongo
mongo = PyMongo(app)

# ==================== COLLECTIONS ====================
# Access collections after mongo initialization
services_collection = mongo.db.services
customers_collection = mongo.db.customers
bills_collection = mongo.db.bills
users_collection = mongo.db.users

# ==================== AUTH DECORATOR ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTH ROUTES ====================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = users_collection.find_one({'username': username, 'password': password})
        if user:
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================
@app.route('/')
@login_required
def dashboard():
    total_customers = customers_collection.count_documents({})
    total_services = services_collection.count_documents({})
    total_bills = bills_collection.count_documents({})
    bills = list(bills_collection.find({'status': 'paid'}))
    total_earnings = sum(bill.get('total_amount', 0) for bill in bills)
    recent_bills = list(bills_collection.find().sort('created_at', -1).limit(5))

    for bill in recent_bills:
        customer = customers_collection.find_one({'_id': ObjectId(bill['customer_id'])})
        bill['customer_name'] = customer['name'] if customer else 'Unknown'

    stats = {
        'total_customers': total_customers,
        'total_services': total_services,
        'total_bills': total_bills,
        'total_earnings': total_earnings
    }
    return render_template('dashboard.html', stats=stats, recent_bills=recent_bills)

# ==================== SERVICES ====================
@app.route('/services')
@login_required
def services():
    all_services = list(services_collection.find())
    return render_template('services.html', services=all_services)

@app.route('/api/services', methods=['POST'])
@login_required
def add_service():
    data = request.get_json()
    service = {
        'name': data['name'],
        'price': float(data['price']),
        'description': data.get('description', ''),
        'created_at': datetime.now()
    }
    result = services_collection.insert_one(service)
    service['_id'] = str(result.inserted_id)
    return jsonify({'success': True, 'service': service})

@app.route('/api/services/<service_id>', methods=['PUT'])
@login_required
def update_service(service_id):
    data = request.get_json()
    services_collection.update_one({'_id': ObjectId(service_id)}, {'$set': {
        'name': data['name'],
        'price': float(data['price']),
        'description': data.get('description', '')
    }})
    return jsonify({'success': True})

@app.route('/api/services/<service_id>', methods=['DELETE'])
@login_required
def delete_service(service_id):
    services_collection.delete_one({'_id': ObjectId(service_id)})
    return jsonify({'success': True})

# ==================== CUSTOMERS ====================
@app.route('/customers')
@login_required
def customers():
    search_query = request.args.get('search', '')
    query = {
        '$or': [
            {'name': {'$regex': search_query, '$options': 'i'}},
            {'phone': {'$regex': search_query, '$options': 'i'}}
        ]
    } if search_query else {}
    all_customers = list(customers_collection.find(query))
    return render_template('customers.html', customers=all_customers, search_query=search_query)

@app.route('/api/customers', methods=['POST'])
@login_required
def add_customer():
    data = request.get_json()
    customer = {
        'name': data['name'],
        'phone': data['phone'],
        'email': data.get('email', ''),
        'created_at': datetime.now()
    }
    result = customers_collection.insert_one(customer)
    customer['_id'] = str(result.inserted_id)
    return jsonify({'success': True, 'customer': customer})

@app.route('/api/customers/<customer_id>', methods=['PUT'])
@login_required
def update_customer(customer_id):
    data = request.get_json()
    customers_collection.update_one({'_id': ObjectId(customer_id)}, {'$set': {
        'name': data['name'],
        'phone': data['phone'],
        'email': data.get('email', '')
    }})
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>', methods=['DELETE'])
@login_required
def delete_customer(customer_id):
    customers_collection.delete_one({'_id': ObjectId(customer_id)})
    return jsonify({'success': True})

# ==================== BILLING ====================
@app.route('/billing')
@login_required
def billing():
    all_customers = list(customers_collection.find())
    all_services = list(services_collection.find())
    return render_template('billing.html', customers=all_customers, services=all_services)

@app.route('/api/bills', methods=['POST'])
@login_required
def create_bill():
    data = request.get_json()
    total_amount = 0
    for service in data['services']:
        service_data = services_collection.find_one({'_id': ObjectId(service['id'])})
        total_amount += service_data['price'] * service['quantity']
    bill = {
        'customer_id': data['customer_id'],
        'services': data['services'],
        'total_amount': total_amount,
        'status': data['status'],
        'created_at': datetime.now(),
        'created_by': session.get('username', 'Unknown')
    }
    result = bills_collection.insert_one(bill)
    bill['_id'] = str(result.inserted_id)
    return jsonify({'success': True, 'bill': bill})

@app.route('/bills')
@login_required
def bills():
    all_bills = list(bills_collection.find().sort('created_at', -1))
    for bill in all_bills:
        customer = customers_collection.find_one({'_id': ObjectId(bill['customer_id'])})
        bill['customer_name'] = customer['name'] if customer else 'Unknown'
        for service in bill['services']:
            service_data = services_collection.find_one({'_id': ObjectId(service['id'])})
            service['name'] = service_data['name'] if service_data else 'Unknown'
            service['price'] = service_data['price'] if service_data else 0
    return render_template('bills.html', bills=all_bills)

@app.route('/api/bills/<bill_id>/status', methods=['PUT'])
@login_required
def update_bill_status(bill_id):
    data = request.get_json()
    bills_collection.update_one({'_id': ObjectId(bill_id)}, {'$set': {'status': data['status']}})
    return jsonify({'success': True})

# ==================== PDF GENERATION ====================
@app.route('/bills/<bill_id>/pdf')
@login_required
def generate_pdf(bill_id):
    bill = bills_collection.find_one({'_id': ObjectId(bill_id)})
    customer = customers_collection.find_one({'_id': ObjectId(bill['customer_id'])})
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica-Bold", 24)
    c.drawString(1*inch, height - 1*inch, "Rushi Salon")
    c.setFont("Helvetica", 10)
    c.drawString(1*inch, height - 1.3*inch, "Invoice / Receipt")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, height - 2*inch, f"Bill ID: {str(bill['_id'])}")
    c.drawString(1*inch, height - 2.3*inch, f"Date: {bill['created_at'].strftime('%Y-%m-%d %H:%M')}")
    c.drawString(1*inch, height - 2.8*inch, f"Customer: {customer['name']} ({customer['phone']})")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, height - 4*inch, "Services:")
    y = height - 4.3*inch
    for s in bill['services']:
        svc = services_collection.find_one({'_id': ObjectId(s['id'])})
        line = f"{svc['name']} x {s['quantity']} - Rs. {svc['price'] * s['quantity']}"
        c.setFont("Helvetica", 11)
        c.drawString(1*inch, y, line)
        y -= 0.3*inch
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1*inch, y - 0.2*inch, f"Total: Rs. {bill['total_amount']}")
    c.drawString(1*inch, y - 0.5*inch, f"Status: {bill['status'].upper()}")
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'bill_{bill_id}.pdf', mimetype='application/pdf')

# ==================== INITIAL DATA ====================
def initialize_database():
    try:
        if users_collection.count_documents({}) == 0:
            users_collection.insert_one({'username': 'admin', 'password': 'admin123', 'role': 'admin', 'created_at': datetime.now()})
            print("✅ Default admin created: admin / admin123")
        if services_collection.count_documents({}) == 0:
            sample_services = [
                {'name': 'Haircut', 'price': 500, 'description': 'Professional haircut', 'created_at': datetime.now()},
                {'name': 'Hair Coloring', 'price': 2500, 'description': 'Full coloring service', 'created_at': datetime.now()},
            ]
            services_collection.insert_many(sample_services)
            print("✅ Sample services added")
    except Exception as e:
        print(f"⚠️ Database initialization error: {e}")
        print("Check your MongoDB connection string and network access settings")

if __name__ == '__main__':
    # Test connection before starting
    try:
        mongo.db.command('ping')
        print("✅ MongoDB connection successful!")
        initialize_database()
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("Please check:")
        print("1. MongoDB Atlas network access (whitelist your IP)")
        print("2. Database user credentials")
        print("3. Connection string format")
    
    app.run(debug=True, port=5000)