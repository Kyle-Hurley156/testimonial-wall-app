import os
import stripe
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# --- CONFIGURATION & INITIALIZATION ---
app = Flask(__name__)
# SECRET_KEY is also best stored as an environment variable for production
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-default-secret-key-for-local-dev')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'testimonials.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- STRIPE API KEYS - SECURELY READ FROM ENVIRONMENT ---
app.config['STRIPE_PUBLIC_KEY'] = os.getenv('STRIPE_PUBLIC_KEY')
app.config['STRIPE_SECRET_KEY'] = os.getenv('STRIPE_SECRET_KEY')
app.config['STRIPE_PRICE_ID'] = os.getenv('STRIPE_PRICE_ID')

stripe.api_key = app.config['STRIPE_SECRET_KEY']


db = SQLAlchemy(app)
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists.')
            return redirect(url_for('signup'))

        new_user = User(email=email)
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
            flash('Please check your login details and try again.')
            return redirect(url_for('login'))
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/submit_page')
@login_required
def submit_page():
    return render_template('submit.html')

@app.route('/submit', methods=['POST'])
@login_required
def submit_testimonial():
    name = request.form['author_name']
    text = request.form['content']
    new_testimonial = Testimonial(author_name=name, content=text, owner=current_user)
    db.session.add(new_testimonial)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    all_testimonials = Testimonial.query.filter_by(user_id=current_user.id).order_by(Testimonial.id.desc()).all()
    return render_template('dashboard.html', testimonials=all_testimonials)

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

# --- STRIPE PAYMENT ROUTES ---
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
            client_reference_id=current_user.id
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


# --- PUBLIC WALL ROUTE ---
@app.route('/wall/<int:user_id>')
def show_wall(user_id):
    user = User.query.get_or_404(user_id)
    approved_testimonials = Testimonial.query.filter_by(owner=user, status='approved').order_by(Testimonial.id.desc()).all()
    return render_template('wall.html', testimonials=approved_testimonials, user=user)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)

