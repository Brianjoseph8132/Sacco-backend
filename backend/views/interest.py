from models import db,LoanRepayment
from flask import jsonify,request, Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import extract, func
import calendar
from decorator import admin_required


interest_bp = Blueprint("interest_bp", __name__)


def get_monthly_interest(session):
    results = session.query(
        extract('year', LoanRepayment.payment_date).label('year'),
        extract('month', LoanRepayment.payment_date).label('month'),
        func.sum(LoanRepayment.interest_component).label('total_interest')
    ).group_by('year', 'month').order_by('year', 'month').all()

    return [
        {
            "year": int(year),
            "month": calendar.month_abbr[int(month)], 
            "interest": float(total_interest or 0)
        }
        for year, month, total_interest in results
    ]

@interest_bp.route('/repayments/interest/monthly', methods=['GET'])
@jwt_required()
@admin_required
def monthly_interest_analysis():
    session = db.session
    data = get_monthly_interest(session)
    return jsonify(data), 200