from flask import Flask, request, jsonify, Blueprint
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from models import db, PdfDocument, SpendingSummary, ReceivedSummary
from datetime import datetime
import os
from collections import defaultdict

summary_bp = Blueprint("summary_bp", __name__)


def generate_and_spend_summary(transactions, pdf_id):
    spending_summary = defaultdict(lambda: {
        'total': 0.0,
        'count': 0,
        'transactions': []
    })

    for txn in transactions:
        withdraw = txn.get("withdrawn", 0.0)

        # Only consider withdrawals (negative values)
        if withdraw >= 0.0:
            continue  

        detail = txn["details"].strip().replace('\n', ' ')
        spending_summary[detail]['total'] += abs(withdraw)
        spending_summary[detail]['count'] += 1

        # Save full txn for drill-down
        spending_summary[detail]['transactions'].append({
            "receipt_no": txn.get("receipt_no"),
            "completion_time": txn.get("completion_time"),
            "details": txn.get("details"),
            "transaction_status": txn.get("transaction_status"),
            "withdrawn": withdraw,
            "balance": txn.get("balance")
        })

    result_list = []
    for detail, values in spending_summary.items():
        # Store aggregated summary in DB
        entry = SpendingSummary(
            pdf_id=pdf_id,
            category=detail,
            total_spent=round(values['total'], 2),
            transaction_count=values['count']
        )
        db.session.add(entry)

        # Response includes drill-down data
        result_list.append({
            "category": detail,
            "total_spent": round(values['total'], 2),
            "transaction_count": values['count'],
            "transactions": values['transactions']   # 👈 added drill-down list
        })

    db.session.commit()
    return result_list


def generate_and_received_summary(transactions, pdf_id):
    received_summary = defaultdict(lambda: {'total': 0.0, 'count': 0, 'transactions': []})

    for txn in transactions:
        if not txn.get("paid_in") or txn["paid_in"] == 0.0:
            continue  # Skip transactions with no incoming amount

        detail = txn["details"].strip().replace('\n', ' ')
        received_summary[detail]['total'] += txn["paid_in"]
        received_summary[detail]['count'] += 1
        received_summary[detail]['transactions'].append(txn)  # keep full transaction

    result_list = []
    for detail, values in received_summary.items():
        entry = ReceivedSummary(
            pdf_id=pdf_id,
            category=detail,
            total_received=round(values['total'], 2),
            transaction_count=values['count']
        )
        db.session.add(entry)

        result_list.append({
            "category": detail,
            "total_received": round(values['total'], 2),
            "transaction_count": values['count'],
            "transactions": values['transactions']  # include full details
        })

    db.session.commit()
    return result_list