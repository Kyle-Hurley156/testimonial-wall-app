import os
import stripe
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION & INITIALIZATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-very-secret-and-secure-key-for-dev')
basedir = os.path.abspath(os.path.dirname(__file__))
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
    subscription_status = db.Column(db.String(50), default='inactive', nullable=False)
    testimonials = db.relationship('Testimonial', backref='owner', lazy=True, cascade="all, delete-orphan")
    wall_title = db.Column(db.String(100), nullable=True)
    wall_description = db.Column(db.Text, nullable=True)
    # --- NEW: Add Stripe Customer ID ---
    stripe_customer_id = db.Column(db.String(100), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=True)

# --- ROUTES ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/collect/<int:user_id>')
def collect_testimonial(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('submit.html', user=user)

@app.route('/submit/<int:user_id>', methods=['POST'])
def submit_for_user(user_id):
    user = User.query.get_or_404(user_id)
    name = request.form['author_name']
    text = request.form['content']
    rating = request.form.get('rating')
    new_testimonial = Testimonial(author_name=name, content=text, rating=rating, owner=user)
    db.session.add(new_testimonial)
    db.session.commit()
    return render_template('success_submit.html')

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

        # --- NEW: Create a customer in Stripe ---
        try:
            customer = stripe.Customer.create(email=email)
        except Exception as e:
            flash(f"Could not create Stripe customer: {e}", "error")
            return redirect(url_for('signup'))

        new_user = User(email=email, stripe_customer_id=customer.id)
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

@app.route('/update_wall_settings', methods=['POST'])
@login_required
def update_wall_settings():
    current_user.wall_title = request.form.get('wall_title')
    current_user.wall_description = request.form.get('wall_description')
    db.session.commit()
    flash('Your wall settings have been updated!', 'success')
    return redirect(url_for('dashboard'))

# ... approve, hide, delete routes ...
@app.route('/approve/<int:testimonial_id>')
@login_required
def approve_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user: return "Unauthorized", 403
    testimonial.status = 'approved'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/hide/<int:testimonial_id>')
@login_required
def hide_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user: return "Unauthorized", 403
    testimonial.status = 'hidden'
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:testimonial_id>')
@login_required
def delete_testimonial(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    if testimonial.owner != current_user: return "Unauthorized", 403
    db.session.delete(testimonial)
    db.session.commit()
    flash('Testimonial has been deleted.', 'success')
    return redirect(url_for('dashboard'))

# --- STRIPE & BILLING ROUTES ---
@app.route('/create-checkout-session')
@login_required
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            # --- UPDATED: Pass the customer ID ---
            customer=current_user.stripe_customer_id,
            line_items=[{'price': app.config['STRIPE_PRICE_ID'], 'quantity': 1}],
            mode='subscription',
            success_url=url_for('success', _external=True),
            cancel_url=url_for('cancel', _external=True),
        )
    except Exception as e: return str(e)
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

# --- NEW: Route to the Stripe Customer Portal ---
@app.route('/manage-subscription')
@login_required
def manage_subscription():
    portal_session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=url_for('dashboard', _external=True)
    )
    return redirect(portal_session.url, code=303)

@app.route('/wall/<int:user_id>')
def show_wall(user_id):
    user = User.query.get_or_404(user_id)
    approved_testimonials = Testimonial.query.filter_by(owner=user, status='approved').order_by(Testimonial.id.desc()).all()
    return render_template('wall.html', testimonials=approved_testimonials, user=user)

