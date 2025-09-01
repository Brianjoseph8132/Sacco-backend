from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, ForeignKey, CheckConstraint
from datetime import datetime
from werkzeug.security import generate_password_hash
from decimal import Decimal
from sqlalchemy import Numeric, CheckConstraint

metadata = MetaData()
db = SQLAlchemy(metadata=metadata)

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_analyst = db.Column (db.Boolean, default=False)
    profile_picture = db.Column(db.String(256), nullable=True, default='https://media.istockphoto.com/id/1337144146/vector/default-avatar-profile-icon-vector.jpg?s=612x612&w=0&k=20&c=BIbFwuv7FxTWvh5S3vB6bkT0Qv8Vn8N5Ffseq84ClGI=')

    account = db.relationship('Account', backref='member', uselist=False, lazy=True)

    # Specify foreign_keys to resolve ambiguity
    loans = db.relationship('Loan', foreign_keys='Loan.member_id', backref='borrower', lazy=True)
    guaranteed_loans = db.relationship(
        'Loan',
        foreign_keys='Loan.guarantor_username',
        primaryjoin='Member.username == Loan.guarantor_username',
        backref='guarantor_member',
        lazy=True
    )
    # approved_loans = db.relationship(
    #     'Loan',
    #     foreign_keys='Loan.approved_by_username',
    #     primaryjoin='Member.username == Loan.approved_by_username',
    #     backref='approver_member',
    #     lazy=True
    # )

    notifications_received = db.relationship(
        'Notification',
        foreign_keys='Notification.recipient_username',
        primaryjoin='Member.username == Notification.recipient_username',
        backref='recipient',
        lazy=True
    )

    notifications_sent = db.relationship('Notification', backref='sender', foreign_keys='Notification.sender_id')



    
class Account(db.Model):
    __tablename__ = 'account'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    balance = db.Column(Numeric(precision=12, scale=2), default=Decimal('0.00'), nullable=False)
    pin = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(20))
    id_number = db.Column(db.String(20), unique=True)
    occupation = db.Column(db.String(100))
    # minimum_balance = db.Column(Numeric(precision=12, scale=2), default=Decimal('100.00'))  # SACCO policy

    # __table_args__ = (
    #     CheckConstraint('balance >= minimum_balance', name='account_min_balance_check'),
    # )

    def set_pin(self, pin):
        self.pin = generate_password_hash(pin)

    def deposit(self, amount):
        amount = Decimal(str(amount))  # convert to Decimal
        self.balance += amount
        transaction = Transaction(type="deposit", amount=amount, account_id=self.id)
        db.session.add(transaction)

    def withdraw(self, amount):
        amount = Decimal(str(amount))  # convert to Decimal
        self.balance -= amount
        transaction = Transaction(type="withdraw", amount=amount, account_id=self.id)
        db.session.add(transaction)

    def __repr__(self):
        return f"<Account {self.id} - Balance: {self.balance}>"


class Transaction(db.Model):
    __tablename__ = 'transaction'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # 'deposit' or 'withdraw'
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)

    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'))

    def __repr__(self):
        return f"<Transaction {self.id} - {self.type} {self.amount}>"

class Loan(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    interest_rate = db.Column(db.Numeric(5, 2), default=12.0)
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    approval_date = db.Column(db.DateTime)
    term_months = db.Column(db.Integer, default=6)
    purpose = db.Column(db.String(100), nullable=False )  # e.g., "Business", "Education"
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected/paid
    guarantor_username = db.Column(db.String(100), db.ForeignKey('members.username'))  # Changed from guarantor_id
    # approved_by_username = db.Column(db.String(100), db.ForeignKey('members.username'))  # Changed from approved_by
     

    repayments = db.relationship('LoanRepayment', backref='loan', lazy=True)
   

    

class LoanRepayment(db.Model):
    __tablename__ = 'loan_repayments'
    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))

    principal_component = db.Column(db.Numeric(10, 2), default=0.0)
    interest_component = db.Column(db.Numeric(10, 2), default=0.0)
    

    

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    recipient_username = db.Column(db.String(100), db.ForeignKey('members.username'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    title = db.Column(db.String(100), nullable=False)  # e.g., "Loan Approved"
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50))  # 'loan_request', 'loan_status_update', 'repayment_notice', etc.
    loan_id = db.Column(db.Integer, db.ForeignKey('loans.id'), nullable=True)

    # Relationship
    loan = db.relationship('Loan', backref='notifications')
    


# class Profile(db.Model):
#     __tablename__ = 'profile'
#     id = db.Column(db.Integer, primary_key=True)
#     member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
#     username = db.Column(db.String(100))
#     email = db.Column(db.String(100))
#     phone = db.Column(db.String(20))
#     password = db.Column(db.String(200))  # hashed
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)


# PDF Document model
class PdfDocument(db.Model):
    __tablename__ = 'pdf_document'  
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    content = db.Column(db.LargeBinary, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Spending Summary model
class SpendingSummary(db.Model):
    __tablename__ = 'spending_summary'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id'), nullable=False, index=True)
    category = db.Column(db.String(255), nullable=False)
    total_spent = db.Column(db.Float, nullable=False)
    transaction_count = db.Column(db.Integer, default=0)

    pdf = db.relationship('PdfDocument', backref=db.backref('spending_summaries', lazy=True))


# Received Summary model
class ReceivedSummary(db.Model):
    __tablename__ = 'received_summary'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id'), nullable=False, index=True)
    category = db.Column(db.String(255), nullable=False)
    total_received = db.Column(db.Float, nullable=False)
    transaction_count = db.Column(db.Integer, default=0)

    pdf = db.relationship('PdfDocument', backref=db.backref('received_summaries', lazy=True))


# # Total Summary model
# class TotalSummary(db.Model):
#     __tablename__ = 'total_summary'
#     id = db.Column(db.Integer, primary_key=True)
#     pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id'), nullable=False, index=True)
#     transaction_type = db.Column(db.String,nullable=False)
#     total_paid_in = db.Column(db.String, nullable=False)
#     total_paid_out = db.Column(db.String, nullable=False)

#     document = db.relationship("PdfDocument", backref="total_summaries")

# Customer Details model
class CustomerDetails(db.Model):
    __tablename__ = 'customer_details'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id'), nullable=False, index=True)
    customer_name = db.Column(db.String, nullable=False)
    mobile_number = db.Column(db.String, nullable=False)
    email_address = db.Column(db.String, nullable=False)
    statement_period = db.Column(db.String, nullable=False)
    request_date = db.Column(db.String, nullable=False)
    statement_duration_months = db.Column(db.Integer, nullable=False)


    document = db.relationship("PdfDocument", backref="customer_details")



class TokenBlocklist(db.Model):
    __tablename__ = 'token_blocklist'
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False)