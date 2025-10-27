import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, abort
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'library.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    
    loans = db.relationship('Loan', back_populates='member')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email
        }

class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    copies = db.Column(db.Integer, default=1, nullable=False)

    loans = db.relationship('Loan', back_populates='book')

    @property
    def available_copies(self):
        active_loans = Loan.query.filter_by(book_id=self.id, return_date=None).count()
        return self.copies - active_loans

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'copies': self.copies,
            'available': self.available_copies 
        }

class Loan(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    
    loan_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    due_date = db.Column(db.Date, nullable=False, default=lambda: (datetime.utcnow().date() + timedelta(days=14)))
    return_date = db.Column(db.Date, nullable=True) 

    member = db.relationship('Member', back_populates='loans')
    book = db.relationship('Book', back_populates='loans')

    def to_dict(self):
        return {
            'id': self.id,
            'member_id': self.member_id,
            'member_name': self.member.name, 
            'book_id': self.book_id,
            'book_title': self.book.title,
            'loan_date': self.loan_date.isoformat(),
            'due_date': self.due_date.isoformat(),
            'return_date': self.return_date.isoformat() if self.return_date else None
        }

@app.route('/api/members', methods=['POST'])
def add_member():
    data = request.get_json()
    if not data or not 'name' in data or not 'email' in data:
        return jsonify({'error': 'Missing data (name, email required)'}), 400


    if Member.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 409

    new_member = Member(name=data['name'], email=data['email'])
    
    db.session.add(new_member)
    db.session.commit()
    
    response_data = new_member.to_dict()
    response = jsonify(response_data)
    response.status_code = 201
    response.headers['Location'] = f'/api/members/{new_member.id}'
    return response

@app.route('/api/members', methods=['GET'])
def get_members():
    members = Member.query.all()
    return jsonify([member.to_dict() for member in members])

@app.route('/api/books', methods=['POST'])
def add_book():
    data = request.get_json()
    if not data or not 'title' in data or not 'author' in data:
        return jsonify({'error': 'Missing data (title, author required)'}), 400

    copies = data.get('copies', 1) 
    
    new_book = Book(
        title=data['title'], 
        author=data['author'], 
        copies=copies
    )
    db.session.add(new_book)
    db.session.commit()

    response_data = new_book.to_dict()
    response = jsonify(response_data)
    response.status_code = 201
    response.headers['Location'] = f'/api/books/{new_book.id}'
    return response

@app.route('/api/books', methods=['GET'])
def get_books():
    books = Book.query.all()
    return jsonify([book.to_dict() for book in books])

@app.route('/api/loans/borrow', methods=['POST'])
def borrow_book():
    data = request.get_json()
    if not data or not 'member_id' in data or not 'book_id' in data:
        return jsonify({'error': 'Missing data (member_id, book_id required)'}), 400

    book = Book.query.get(data['book_id'])
    member = Member.query.get(data['member_id'])

    if not book or not member:
        return jsonify({'error': 'Member or Book not found'}), 404

    if book.available_copies <= 0:
        return jsonify({'error': 'No available copies of this book'}), 409

    
    days = data.get('days', 14) 
    due_date = datetime.utcnow().date() + timedelta(days=int(days))
    
    new_loan = Loan(
        member_id=member.id,
        book_id=book.id,
        due_date=due_date
    )
    
    db.session.add(new_loan)
    db.session.commit()
    
    response_data = new_loan.to_dict()
    response = jsonify(response_data)
    response.status_code = 201
    response.headers['Location'] = f'/api/loans/{new_loan.id}'
    return response

@app.route('/api/loans/return', methods=['POST'])
def return_book():
    data = request.get_json()
    if not data or not 'loan_id' in data:
        return jsonify({'error': 'Missing data (loan_id required)'}), 400
        
    loan = Loan.query.get(data['loan_id'])
    
    if not loan:
        return jsonify({'error': 'Loan not found'}), 404

    if loan.return_date is not None:
        return jsonify({'error': 'Book already returned'}), 409

    loan.return_date = datetime.utcnow().date()
    db.session.commit()
    
    return jsonify(loan.to_dict()), 200

@app.route('/api/loans', methods=['GET'])
def get_loans():
    loans = Loan.query.filter_by(return_date=None).all()
    
    return jsonify([loan.to_dict() for loan in loans])


@app.route('/')
def index():
    try:
        return app.send_static_file('index.html')
    except:
        return "Umieść plik index.html w folderze 'static', aby zobaczyć UI."

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
        
    with app.app_context():
        db.create_all()
        
    app.run(debug=True, port=5000)