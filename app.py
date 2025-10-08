import os
import stripe
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION & INITIALIZATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-very-secret-and-secure-key-for-dev')
# This is a simple secret to protect your admin page. Change it to something unique.
app.config['ADMIN_KEY'] = os.getenv('ADMIN_KEY', 'super-secret-admin-key') 
basedir = os.path.abspath(os.path.dirname(__file__))

# --- DATABASE CONFIGURATION ---
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'testimonials.db'))
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- STRIPE API KEYS ---
app.config['STRIPE_PUBLIC_KEY'] = os.getenv('STRIPE_PUBLIC_KEY', 'pk_test_51SFS5S3toE0KJFCbXVfgIk16o4nCrOzayqQtPnrpXWUmB9M0X9ml4pc1M5DZz897MQ3xMfD3S8ZM4I74SwGkf9Ey00oTeIJIoz')
app.config['STRIPE_SECRET_KEY'] = os.getenv('STRIPE_SECRET_KEY', 'sk_test_51SFS5S3toE0KJFCbIlZaFDbvBx522bChisDBtF3pjD8WDAd6NgT8wwLpxpJuA1Rj5MaEggTIzFgYhABO3PjM2rm600YcMHRLg3')
app.config['STRIPE_PRICE_ID'] = os.getenv('STRIPE_PRICE_ID', 'price_1SFS8p3toE0KJFCbIdQuUl1F')

stripe.api_key = app.config['STRIPE_SECRET_KEY']

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- DATABASE MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    # The status can now be 'inactive', 'active' (monthly), or 'lifetime'
    subscription_status = db.Column(db.String(50), default='inactive', nullable=False) 
    stripe_customer_id = db.Column(db.String(100))
    wall_title = db.Column(db.String(100))
    testimonials = db.relationship('Testimonial', backref='owner', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    rating = db.Column(db.Integer, default=5)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# New PromoCode model
class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    redeemed_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

# --- NEW ADMIN ROUTE ---
@app.route('/admin/<admin_key>', methods=['GET', 'POST'])
def admin(admin_key):
    if admin_key != app.config['ADMIN_KEY']:
        return "Unauthorized", 403

    if request.method == 'POST':
        # Generate a new unique code
        new_code_str = secrets.token_hex(8).upper()
        new_code = PromoCode(code=new_code_str)
        db.session.add(new_code)
        db.session.commit()
        flash(f'New code generated: {new_code_str}', 'success')

    all_codes = PromoCode.query.all()
    return render_template('admin.html', codes=all_codes)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists.', 'error')
            return redirect(url_for('signup'))

        # Create Stripe customer first
        try:
            customer = stripe.Customer.create(email=email)
            stripe_customer_id = customer.id
        except Exception as e:
            flash(f'Could not create billing account: {e}', 'error')
            return redirect(url_for('signup'))

        new_user = User(email=email, stripe_customer_id=stripe_customer_id)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            flash('Please check your login details and try again.', 'error')
            return redirect(url_for('login'))
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    all_testimonials = Testimonial.query.filter_by(user_id=current_user.id).order_by(Testimonial.id.desc()).all()
    return render_template('dashboard.html', testimonials=all_testimonials)

# --- NEW CODE REDEMPTION ROUTE ---
@app.route('/redeem-code', methods=['POST'])
@login_required
def redeem_code():
    code_str = request.form.get('promo_code')
    
    if not code_str:
        flash('Please enter a code.', 'error')
        return redirect(url_for('dashboard'))
        
    promo_code = PromoCode.query.filter_by(code=code_str.upper()).first()

    if not promo_code:
        flash('Invalid promotional code.', 'error')
        return redirect(url_for('dashboard'))

    if not promo_code.is_active:
        flash('This code has already been used.', 'error')
        return redirect(url_for('dashboard'))

    if current_user.subscription_status in ['active', 'lifetime']:
         flash('You already have an active or lifetime subscription.', 'error')
         return redirect(url_for('dashboard'))

    # Success! Apply the lifetime access
    promo_code.is_active = False
    promo_code.redeemed_by_user_id = current_user.id
    current_user.subscription_status = 'lifetime'
    
    db.session.commit()
    flash('Congratulations! You now have free lifetime access.', 'success')
    return redirect(url_for('dashboard'))

# (The rest of your routes remain the same)
@app.route('/collect/<int:user_id>', methods=['GET', 'POST'])
def collect_testimonial(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        name = request.form['author_name']
        text = request.form['content']
        rating = int(request.form.get('rating', 5))
        new_testimonial = Testimonial(author_name=name, content=text, rating=rating, owner=user)
        db.session.add(new_testimonial)
        db.session.commit()
        return redirect(url_for('success_submit'))
    return render_template('submit.html', user=user)

@app.route('/success-submit')
def success_submit():
    return render_template('success_submit.html')

@app.route('/update-wall-settings', methods=['POST'])
@login_required
def update_wall_settings():
    title = request.form.get('wall_title')
    current_user.wall_title = title
    db.session.commit()
    flash('Your wall settings have been updated.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/approve/<int:testimonial_id>')
@login_required
def approve_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user:
        return "Unauthorized", 403
    testimonial.status = 'approved'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/hide/<int:testimonial_id>')
@login_required
def hide_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user:
        return "Unauthorized", 403
    testimonial.status = 'hidden'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:testimonial_id>')
@login_required
def delete_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user:
        return "Unauthorized", 403
    db.session.delete(testimonial)
    db.session.commit()
    flash('Testimonial has been deleted.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/create-checkout-session')
@login_required
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': app.config['STRIPE_PRICE_ID'],
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=url_for('success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('cancel', _external=True),
            customer=current_user.stripe_customer_id
        )
    except Exception as e:
        return str(e)

    return redirect(checkout_session.url, code=303)

@app.route('/success')
@login_required
def success():
    current_user.subscription_status = 'active'
    db.session.commit()
    return render_template('success.html')

@app.route('/cancel')
@login_required
def cancel():
    return render_template('cancel.html')

@app.route('/manage-subscription')
@login_required
def manage_subscription():
    try:
        session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=url_for('dashboard', _external=True),
        )
        return redirect(session.url)
    except Exception as e:
        flash(f"Could not open billing portal: {e}", "error")
        return redirect(url_for('dashboard'))

@app.route('/wall/<int:user_id>')
def show_wall(user_id):
    user = User.query.get_or_404(user_id)
    approved_testimonials = Testimonial.query.filter_by(owner=user, status='approved').order_by(Testimonial.id.desc()).all()
    return render_template('wall.html', testimonials=approved_testimonials, user=user)

if __name__ == '__main__':
    app.run(debug=True)

