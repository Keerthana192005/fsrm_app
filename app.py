from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import inspect, text
import os
from datetime import datetime
from models import db, Vegetable, Order, OrderItem, Feedback, Admin
from config import config
from utils import generate_payment_qr_code
import logging

def ensure_feedback_rating_column():
    inspector = inspect(db.engine)
    if 'feedback' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('feedback')]
        if 'rating' not in columns:
            if db.engine.dialect.name == 'sqlite':
                db.session.execute(text('ALTER TABLE feedback ADD COLUMN rating INTEGER DEFAULT 5'))
            else:
                db.session.execute(text('ALTER TABLE feedback ADD COLUMN rating INTEGER DEFAULT 5'))
            db.session.commit()


def create_app(config_name=None):
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    
    # Configure logging
    if not app.debug:
        logging.basicConfig(filename='app.log', level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO)
    
    app.logger = logging.getLogger(__name__)
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        ensure_feedback_rating_column()
    
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

@app.route('/vegetables')
def vegetables():
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
        rating = request.form.get('rating', type=int)
        
        if not name or not message:
            flash('Please fill in all required fields!', 'error')
            return redirect(url_for('contact'))
        
        if rating is None or rating < 1 or rating > 5:
            rating = 5
        
        # Save feedback to database
        feedback = Feedback(name=name, email=email, rating=rating, message=message)
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
        payment_method = request.form.get('payment_method', 'cod')
        
        # Basic validation
        import re
        if not customer_name or len(customer_name.strip()) < 2:
            flash('Please enter a valid name (at least 2 characters)', 'error')
            return redirect(url_for('checkout'))
        
        if not phone or not re.match(r'^\d{10}$', phone):
            flash('Please enter a valid 10-digit phone number', 'error')
            return redirect(url_for('checkout'))
        
        if not address or len(address.strip()) < 5:
            flash('Please enter a complete delivery address', 'error')
            return redirect(url_for('checkout'))
        
        if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            flash('Please enter a valid email address', 'error')
            return redirect(url_for('checkout'))
        
        if payment_method not in ['cod', 'upi', 'qr']:
            flash('Please select a valid payment method', 'error')
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
        
        # Use transaction for atomic operation
        try:
            with db.session.begin_nested():
                # Check stock availability again and update atomically
                for item_data in order_items_data:
                    veg = item_data['vegetable']
                    if veg.stock < item_data['quantity']:
                        raise ValueError(f'Insufficient stock for {veg.name}')
                    veg.stock -= item_data['quantity']
                
                # Create order
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
                db.session.flush()  # Get order.id
                
                # Create order items
                for item_data in order_items_data:
                    order_item = OrderItem(
                        order_id=order.id,
                        vegetable_id=item_data['vegetable'].id,
                        quantity=item_data['quantity'],
                        price=item_data['price']
                    )
                    db.session.add(order_item)
                
                db.session.commit()
                session['cart'] = {}
                if payment_method == 'cod':
                    flash('Your order has been placed successfully. Please keep the amount ready for delivery.', 'success')
                    return redirect(url_for('order_confirmation', order_id=order.id))
                else:
                    flash('Your order has been created. Please complete payment to confirm your order.', 'success')
                    return redirect(url_for('payment', order_id=order.id))
        except ValueError as e:
            db.session.rollback()
            app.logger.warning(f"Checkout failed for {customer_name}: {str(e)}")
            flash(str(e), 'error')
            return redirect(url_for('checkout'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Checkout error for {customer_name}: {str(e)}")
            flash('An error occurred while processing your order. Please try again.', 'error')
            return redirect(url_for('checkout'))
    
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
    
    if payment_method == 'cod':
        # COD is already handled in checkout
        return redirect(url_for('order_confirmation', order_id=order.id))
    elif payment_method == 'qr':
        return redirect(url_for('qr_payment', order_id=order.id))
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
    
    # Complete the order after the customer confirms payment
    order.payment_method = 'upi'
    order.payment_status = 'completed'
    order.status = 'confirmed'
    
    # Stock is already updated during checkout
    db.session.commit()
    
    # Clear cart for the session
    session['cart'] = {}
    
    app.logger.info(f"Order {order.id} payment confirmed for {order.customer_name}")
    flash('Payment confirmed! Your order is complete.', 'success')
    return redirect(url_for('order_confirmation', order_id=order.id))

@app.route('/order_confirmation/<int:order_id>')
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    order_items = []
    for item in order.order_items:
        order_items.append({
            'vegetable': item.vegetable,
            'quantity': item.quantity,
            'price': item.price,
            'subtotal': item.price * item.quantity
        })
    session['cart'] = {}
    return render_template('order_confirmation.html', order=order, order_items=order_items)

@app.route('/track_order')
def track_order():
    order_id = request.args.get('order_id', type=int)
    email = request.args.get('email')
    if order_id and email:
        order = Order.query.filter_by(id=order_id, email=email).first()
        if order:
            order_items = []
            for item in order.order_items:
                order_items.append({
                    'vegetable': item.vegetable,
                    'quantity': item.quantity,
                    'price': item.price,
                    'subtotal': item.price * item.quantity
                })
            return render_template('order_status.html', order=order, order_items=order_items)
        flash('Order not found. Please verify your Order ID and email.', 'error')
    return render_template('track_order.html')

@app.route('/razorpay_success/<int:order_id>', methods=['POST'])
def razorpay_success(order_id):
    order = Order.query.get_or_404(order_id)
    order.payment_method = 'razorpay'
    order.payment_status = 'completed'
    order.status = 'confirmed'
    db.session.commit()
    session['cart'] = {}
    flash('Payment successful! Your order is confirmed.', 'success')
    return redirect(url_for('order_confirmation', order_id=order.id))

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
        total_feedbacks = Feedback.query.count()
    except Exception as e:
        # Handle case where tables don't exist yet
        print(f"Database error: {e}")
        orders = []
        total_orders = 0
        pending_orders = 0
        feedbacks = []
        total_vegetables = 0
        total_feedbacks = 0
    
    return render_template('admin_dashboard.html', 
                         orders=orders, 
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         feedbacks=feedbacks,
                         total_vegetables=total_vegetables,
                         total_feedbacks=total_feedbacks)

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

@app.route('/admin/update_order_status/<int:order_id>')
@login_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'completed'
    db.session.commit()
    flash(f'Order {order_id} marked as completed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reports')
@login_required
def admin_reports():
    try:
        total_orders = Order.query.count()
        completed_orders = Order.query.filter_by(status='completed').count()
        pending_orders = Order.query.filter_by(status='pending').count()
        total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
        total_customers = len({(order.customer_name, order.phone, order.email) for order in Order.query.all()})
        recent_orders = Order.query.order_by(Order.date.desc()).limit(10).all()
    except Exception as e:
        print(f"Database error: {e}")
        total_orders = completed_orders = pending_orders = total_revenue = total_customers = 0
        recent_orders = []

    return render_template('admin_reports.html',
                           total_orders=total_orders,
                           completed_orders=completed_orders,
                           pending_orders=pending_orders,
                           total_revenue=total_revenue,
                           total_customers=total_customers,
                           recent_orders=recent_orders)

@app.route('/admin/customers')
@login_required
def admin_customers():
    try:
        orders = Order.query.order_by(Order.date.desc()).all()
        unique_customers = {}
        for order in orders:
            key = (order.customer_name, order.phone, order.email)
            if key not in unique_customers:
                unique_customers[key] = {
                    'name': order.customer_name,
                    'phone': order.phone,
                    'email': order.email,
                    'orders': 0,
                    'last_order': order.date
                }
            unique_customers[key]['orders'] += 1
            if order.date > unique_customers[key]['last_order']:
                unique_customers[key]['last_order'] = order.date
    except Exception as e:
        print(f"Database error: {e}")
        unique_customers = {}

    return render_template('admin_customers.html', customers=unique_customers.values())

@app.route('/admin/images')
@login_required
def admin_images():
    images = {
        'bhooswarga': 'bhooswarga_garden.png',
        'dr_sumaraj': 'dr_sumaraj.png',
        'byre_gowda': 'byre_gowda.png',
        'vishwadeep_k': 'vishwadeep_k.jpg',
        'abhishek_r': 'abhishek_r.jpg'
    }
    return render_template('admin_images.html', images=images)

@app.route('/admin/upload_image', methods=['POST'])
@login_required
def upload_image():
    target = request.form.get('target')
    file = request.files.get('image')

    allowed_targets = {
        'bhooswarga': 'bhooswarga_garden.png',
        'dr_sumaraj': 'dr_sumaraj.png',
        'byre_gowda': 'byre_gowda.png',
        'vishwadeep_k': 'vishwadeep_k.jpg',
        'abhishek_r': 'abhishek_r.jpg'
    }

    if target not in allowed_targets:
        flash('Invalid image target.', 'error')
        return redirect(url_for('admin_images'))

    if not file or file.filename == '':
        flash('No image selected.', 'error')
        return redirect(url_for('admin_images'))

    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {'.png', '.jpg', '.jpeg', '.gif'}:
        flash('Unsupported image format. Use PNG/JPG/GIF.', 'error')
        return redirect(url_for('admin_images'))

    save_name = allowed_targets[target]
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], save_name)
    file.save(save_path)

    flash(f'Updated image for {target}.', 'success')
    return redirect(url_for('admin_images'))


def create_tables_and_seed():
    with app.app_context():
        db.create_all()
        ensure_feedback_rating_column()
        
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
            print("Database seeded with sample vegetables!")

if __name__ == '__main__':
    create_tables_and_seed()
    app.run(debug=True, host='127.0.0.1', port=8080)
