from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from models import db, Vegetable, Order, OrderItem, Feedback, Admin
from config import config
from utils import generate_payment_qr_code

def create_app(config_name=None):
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    db.init_app(app)
    
    return app

# Create app instance first
app = create_app()

# Now define all routes using the created app
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

@app.route('/')
def home():
    vegetables = Vegetable.query.filter(Vegetable.stock > 0).all()
    return render_template('home.html', vegetables=vegetables)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/vision')
def vision():
    return render_template('vision.html')

@app.route('/process')
def process():
    return render_template('process.html')

@app.route('/api/vegetables')
def api_vegetables():
    vegetables = Vegetable.query.all()
    return jsonify([veg.to_dict() for veg in vegetables])

@app.route('/api/cart-count')
def api_cart_count():
    cart = session.get('cart', {})
    return jsonify({'count': len(cart)})

@app.route('/cart')
def cart():
    cart_items = session.get('cart', {})
    cart_total = 0
    cart_details = []
    
    for veg_id, item in cart_items.items():
        vegetable = Vegetable.query.get(int(veg_id))
        if vegetable:
            subtotal = vegetable.price * item['quantity']
            cart_total += subtotal
            cart_details.append({
                'vegetable': vegetable,
                'quantity': item['quantity'],
                'subtotal': subtotal
            })
    
    return render_template('cart.html', cart_items=cart_details, cart_total=cart_total)

@app.route('/add_to_cart/<int:veg_id>')
def add_to_cart(veg_id):
    vegetable = Vegetable.query.get_or_404(veg_id)
    
    if vegetable.stock <= 0:
        flash('This vegetable is out of stock!', 'error')
        return redirect(url_for('home'))
    
    cart = session.get('cart', {})
    
    if str(veg_id) in cart:
        if cart[str(veg_id)]['quantity'] < vegetable.stock:
            cart[str(veg_id)]['quantity'] += 1
            flash(f'{vegetable.name} added to cart!', 'success')
        else:
            flash(f'Only {vegetable.stock} {vegetable.name}(s) available in stock!', 'error')
    else:
        cart[str(veg_id)] = {'quantity': 1}
        flash(f'{vegetable.name} added to cart!', 'success')
    
    session['cart'] = cart
    return redirect(url_for('home'))

@app.route('/update_cart', methods=['POST'])
def update_cart():
    veg_id = request.form.get('veg_id')
    quantity = request.form.get('quantity', type=int)
    
    if quantity <= 0:
        cart = session.get('cart', {})
        if str(veg_id) in cart:
            del cart[str(veg_id)]
        session['cart'] = cart
        return jsonify({'success': True, 'message': 'Item removed from cart'})
    
    vegetable = Vegetable.query.get(veg_id)
    if not vegetable or quantity > vegetable.stock:
        return jsonify({'success': False, 'message': 'Invalid quantity or insufficient stock'})
    
    cart = session.get('cart', {})
    cart[str(veg_id)] = {'quantity': quantity}
    session['cart'] = cart
    
    # Calculate new totals
    cart_total = 0
    for item_veg_id, item in cart.items():
        veg = Vegetable.query.get(int(item_veg_id))
        if veg:
            cart_total += veg.price * item['quantity']
    
    return jsonify({
        'success': True, 
        'message': 'Cart updated',
        'subtotal': vegetable.price * quantity,
        'cart_total': cart_total
    })

@app.route('/remove_from_cart/<int:veg_id>')
def remove_from_cart(veg_id):
    cart = session.get('cart', {})
    if str(veg_id) in cart:
        del cart[str(veg_id)]
        session['cart'] = cart
        flash('Item removed from cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        if not all([name, email, message]):
            flash('Please fill in all required fields!', 'error')
            return redirect(url_for('contact'))
        
        # Save feedback to database
        feedback = Feedback(name=name, email=email, message=message)
        db.session.add(feedback)
        db.session.commit()
        
        flash('Thank you for your feedback!', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_items = session.get('cart', {})
    
    if not cart_items:
        flash('Your cart is empty!', 'error')
        return redirect(url_for('cart'))
    
    if request.method == 'POST':
        customer_name = request.form.get('customer_name')
        phone = request.form.get('phone')
        address = request.form.get('address')
        email = request.form.get('email')
        delivery_time = request.form.get('delivery_time')
        order_notes = request.form.get('notes')
        payment_method = request.form.get('payment_method')
        
        if not all([customer_name, phone, address]):
            flash('Please fill in all required fields!', 'error')
            return redirect(url_for('checkout'))
        
        # Calculate total and create order
        total = 0
        order_items_data = []
        
        for veg_id, item in cart_items.items():
            vegetable = Vegetable.query.get(int(veg_id))
            if vegetable:
                subtotal = vegetable.price * item['quantity']
                total += subtotal
                order_items_data.append({
                    'vegetable': vegetable,
                    'quantity': item['quantity'],
                    'price': vegetable.price
                })
        
        # Create order (but don't commit yet for QR payment)
        order = Order(
            customer_name=customer_name,
            phone=phone,
            address=address,
            email=email,
            total=total,
            payment_method=payment_method,
            delivery_time=delivery_time,
            order_notes=order_notes
        )
        db.session.add(order)
        db.session.commit()
        
        # Create order items (but don't commit yet for QR payment)
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                vegetable_id=item_data['vegetable'].id,
                quantity=item_data['quantity'],
                price=item_data['price']
            )
            db.session.add(order_item)
        
        db.session.commit()
        
        # Handle different payment methods
        if payment_method == 'upi':
            return redirect(url_for('payment', order_id=order.id))
        elif payment_method == 'qr':
            return redirect(url_for('qr_payment', order_id=order.id))
        elif payment_method == 'cod':
            # For COD, update stock and clear cart immediately
            for veg_id, item in cart_items.items():
                vegetable = Vegetable.query.get(int(veg_id))
                if vegetable:
                    vegetable.stock -= item['quantity']
            db.session.commit()
            
            # Clear cart
            session['cart'] = {}
            
            flash(f'Order placed successfully! Order ID: {order.id}', 'success')
            return redirect(url_for('order_confirmation', order_id=order.id))
        
        return redirect(url_for('payment', order_id=order.id))
    
    # Calculate total for display
    cart_total = 0
    cart_details = []
    
    for veg_id, item in cart_items.items():
        vegetable = Vegetable.query.get(int(veg_id))
        if vegetable:
            subtotal = vegetable.price * item['quantity']
            cart_total += subtotal
            cart_details.append({
                'vegetable': vegetable,
                'quantity': item['quantity'],
                'subtotal': subtotal
            })
    
    return render_template('checkout.html', cart_items=cart_details, cart_total=cart_total)

@app.route('/payment/<int:order_id>')
def payment(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Get cart items for display
    cart_items = []
    cart_total = 0
    
    # Reconstruct cart from order items
    for item in order.order_items:
        cart_total += item.price * item.quantity
        cart_items.append({
            'vegetable': item.vegetable,
            'quantity': item.quantity,
            'subtotal': item.price * item.quantity
        })
    
    return render_template('payment.html', order=order, cart_items=cart_items, cart_total=cart_total)

@app.route('/process_payment/<int:order_id>', methods=['POST'])
def process_payment(order_id):
    order = Order.query.get_or_404(order_id)
    payment_method = request.form.get('payment_method')
    
    if payment_method == 'razorpay':
        # Razorpay integration
        return redirect(url_for('razorpay_payment', order_id=order.id))
    elif payment_method == 'payu':
        # PayU integration
        return redirect(url_for('payu_payment', order_id=order_id))
    elif payment_method == 'phonepe':
        # PhonePe integration
        return redirect(url_for('phonepe_payment', order_id=order_id))
    else:
        flash('Invalid payment method selected!', 'error')
        return redirect(url_for('payment', order_id=order_id))

@app.route('/qr_payment/<int:order_id>')
def qr_payment(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Get cart items for display
    cart_items = []
    cart_total = 0
    
    # Reconstruct cart from order items
    for item in order.order_items:
        cart_total += item.price * item.quantity
        cart_items.append({
            'vegetable': item.vegetable,
            'quantity': item.quantity,
            'subtotal': item.price * item.quantity
        })
    
    # Generate QR code
    qr_data = generate_payment_qr_code(order_id, cart_total)
    
    return render_template('qr_payment.html', order=order, cart_items=cart_items, cart_total=cart_total, qr_data=qr_data)

@app.route('/verify_qr_payment/<int:order_id>', methods=['POST'])
def verify_qr_payment(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Get payment verification data
    transaction_id = request.form.get('transaction_id')
    upi_id = request.form.get('upi_id')
    amount = request.form.get('amount')
    
    if not all([transaction_id, upi_id, amount]):
        flash('Please provide payment details!', 'error')
        return redirect(url_for('qr_payment', order_id=order_id))
    
    # Verify amount matches order total
    if float(amount) != order.total:
        flash('Payment amount does not match order total!', 'error')
        return redirect(url_for('qr_payment', order_id=order_id))
    
    # Update order with payment details
    order.payment_method = 'upi'
    order.payment_status = 'completed'
    order.payment_id = transaction_id
    order.status = 'confirmed'
    
    # Update stock
    for item in order.order_items:
        vegetable = Vegetable.query.get(item.vegetable_id)
        if vegetable:
            vegetable.stock -= item.quantity
    
    db.session.commit()
    
    # Clear cart
    session['cart'] = {}
    
    flash('Payment successful! Your order has been confirmed.', 'success')
    return redirect(url_for('order_confirmation', order_id=order.id))

@app.route('/order_confirmation/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Get order items for display
    order_items = []
    for item in order.order_items:
        order_items.append({
            'vegetable': item.vegetable,
            'quantity': item.quantity,
            'price': item.price,
            'subtotal': item.price * item.quantity
        })
    
    return render_template('order_confirmation.html', order=order, order_items=order_items)

# Admin routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and admin.check_password(password):
            login_user(admin)
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin/change_password', methods=['GET', 'POST'])
@login_required
def admin_change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            flash('Please fill in all fields!', 'error')
            return redirect(url_for('admin_change_password'))
        
        if new_password != confirm_password:
            flash('New passwords do not match!', 'error')
            return redirect(url_for('admin_change_password'))
        
        admin = Admin.query.get(current_user.id)
        if admin and admin.check_password(current_password):
            admin.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Current password is incorrect!', 'error')
    
    return render_template('admin_change_password.html')

@app.route('/admin/change_username', methods=['POST'])
def change_username():
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_username = data.get('new_username')
        
        if not current_password or not new_username:
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Get the admin user (assuming there's only one admin)
        admin = Admin.query.first()
        if not admin:
            return jsonify({'success': False, 'error': 'Admin not found'})
        
        # Verify current password
        if not admin.check_password(current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'})
        
        # Check if new username already exists
        existing_admin = Admin.query.filter_by(username=new_username).first()
        if existing_admin and existing_admin.id != admin.id:
            return jsonify({'success': False, 'error': 'Username already exists'})
        
        # Update username
        admin.username = new_username
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Username changed successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Failed to change username'})

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    try:
        orders = Order.query.order_by(Order.date.desc()).all()
        total_orders = Order.query.count()
        pending_orders = Order.query.filter_by(status='pending').count()
        feedbacks = Feedback.query.order_by(Feedback.date.desc()).limit(5).all()
        total_vegetables = Vegetable.query.count()
    except Exception as e:
        # Handle case where tables don't exist yet
        print(f"Database error: {e}")
        orders = []
        total_orders = 0
        pending_orders = 0
        feedbacks = []
        total_vegetables = 0
    
    return render_template('admin_dashboard.html', 
                         orders=orders, 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         feedbacks=feedbacks,
                         total_vegetables=total_vegetables)

@app.route('/admin/products')
@login_required
def admin_products():
    try:
        vegetables = Vegetable.query.all()
    except Exception as e:
        print(f"Database error: {e}")
        vegetables = []
    return render_template('admin_products.html', vegetables=vegetables)

@app.route('/admin/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price', type=float)
        stock = request.form.get('stock', type=int)
        description = request.form.get('description')
        
        if not all([name, price, stock]):
            flash('Please fill in all required fields!', 'error')
            return redirect(url_for('add_product'))
        
        # Handle image upload
        image = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename
        
        vegetable = Vegetable(
            name=name,
            price=price,
            stock=stock,
            image=image,
            description=description
        )
        db.session.add(vegetable)
        db.session.commit()
        
        flash(f'{name} added successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('add_product.html')

@app.route('/admin/edit_product/<int:veg_id>', methods=['GET', 'POST'])
@login_required
def edit_product(veg_id):
    vegetable = Vegetable.query.get_or_404(veg_id)
    
    if request.method == 'POST':
        vegetable.name = request.form.get('name')
        vegetable.price = request.form.get('price', type=float)
        vegetable.stock = request.form.get('stock', type=int)
        vegetable.description = request.form.get('description')
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                vegetable.image = filename
        
        db.session.commit()
        flash(f'{vegetable.name} updated successfully!', 'success')
        return redirect(url_for('admin_products'))
    
    return render_template('edit_product.html', vegetable=vegetable)

@app.route('/admin/delete_product/<int:veg_id>')
@login_required
def delete_product(veg_id):
    vegetable = Vegetable.query.get_or_404(veg_id)
    db.session.delete(vegetable)
    db.session.commit()
    flash(f'{vegetable.name} deleted successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/reports')
@login_required
def admin_reports():
    try:
        # Get report data
        total_orders = Order.query.count()
        completed_orders = Order.query.filter_by(status='completed').count()
        pending_orders = Order.query.filter_by(status='pending').count()
        total_revenue = db.session.query(db.func.sum(Order.total)).filter_by(status='completed').scalar() or 0
        total_customers = db.session.query(db.func.count(db.func.distinct(Order.customer_name))).scalar() or 0
        
        # Get monthly sales data
        monthly_sales = db.session.query(
            db.func.date_trunc('month', Order.date).label('month'),
            db.func.sum(Order.total).label('revenue'),
            db.func.count(Order.id).label('orders')
        ).group_by(db.func.date_trunc('month', Order.date)).order_by(db.func.date_trunc('month', Order.date).desc()).limit(6).all()
        
        # Get top selling products
        top_products = db.session.query(
            Vegetable.name,
            db.func.sum(OrderItem.quantity).label('total_sold')
        ).join(OrderItem).group_by(Vegetable.name).order_by(db.func.sum(OrderItem.quantity).desc()).limit(5).all()
        
    except Exception as e:
        print(f"Error generating reports: {e}")
        total_orders = completed_orders = pending_orders = 0
        total_revenue = total_customers = 0
        monthly_sales = []
        top_products = []
    
    return render_template('admin_reports.html', 
                         total_orders=total_orders,
                         completed_orders=completed_orders,
                         pending_orders=pending_orders,
                         total_revenue=total_revenue,
                         total_customers=total_customers,
                         monthly_sales=monthly_sales,
                         top_products=top_products)

@app.route('/admin/customers')
@login_required
def admin_customers():
    try:
        # Get unique customers with their order details
        customers = db.session.query(
            Order.customer_name,
            Order.phone,
            Order.address,
            Order.email,
            db.func.count(Order.id).label('order_count'),
            db.func.sum(Order.total).label('total_spent'),
            db.func.max(Order.date).label('last_order')
        ).group_by(Order.customer_name, Order.phone, Order.address, Order.email).order_by(db.func.max(Order.date).desc()).all()
    except Exception as e:
        print(f"Error fetching customers: {e}")
        customers = []
    
    return render_template('admin_customers.html', customers=customers)

@app.route('/admin/settings')
@login_required
def admin_settings():
    return render_template('admin_settings.html')

@app.route('/admin/update_order_status/<int:order_id>')
@login_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'completed'
    db.session.commit()
    flash(f'Order {order_id} marked as completed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.before_request
def initialize_database():
    """Initialize database tables and seed data on first request"""
    try:
        # Create tables
        db.create_all()
        
        # Create default admin if not exists
        if Admin.query.count() == 0:
            default_admin = Admin(username='admin')
            default_admin.set_password('admin123')
            db.session.add(default_admin)
            db.session.commit()
            print("Default admin account created: username='admin', password='admin123'")
        
        # Seed data if database is empty
        if Vegetable.query.count() == 0:
            seed_data = [
                {'name': 'Tomatoes', 'price': 40.0, 'stock': 50, 'description': 'Fresh red tomatoes from our farm'},
                {'name': 'Potatoes', 'price': 30.0, 'stock': 100, 'description': 'High quality potatoes'},
                {'name': 'Onions', 'price': 35.0, 'stock': 75, 'description': 'Fresh onions'},
                {'name': 'Carrots', 'price': 45.0, 'stock': 60, 'description': 'Sweet and crunchy carrots'},
                {'name': 'Spinach', 'price': 25.0, 'stock': 40, 'description': 'Fresh green spinach'},
                {'name': 'Broccoli', 'price': 60.0, 'stock': 30, 'description': 'Organic broccoli'},
                {'name': 'Bell Peppers', 'price': 55.0, 'stock': 45, 'description': 'Colorful bell peppers'},
                {'name': 'Cucumbers', 'price': 35.0, 'stock': 55, 'description': 'Fresh cucumbers'},
                {'name': 'Cabbage', 'price': 28.0, 'stock': 35, 'description': 'Green cabbage'},
                {'name': 'Cauliflower', 'price': 50.0, 'stock': 25, 'description': 'Fresh cauliflower'}
            ]
            
            for data in seed_data:
                vegetable = Vegetable(**data)
                db.session.add(vegetable)
            
            db.session.commit()
            print("Database seeded with initial vegetable data")
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        db.session.rollback()

# Make the function available at module level for backward compatibility
def create_tables_and_seed(app_instance):
    with app_instance.app_context():
        initialize_database()

if __name__ == '__main__':
    create_tables_and_seed(app)
    app.run(debug=True, host='127.0.0.1', port=8080)
