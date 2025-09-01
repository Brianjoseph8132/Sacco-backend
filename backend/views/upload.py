from flask import Flask, request, jsonify, Blueprint
from werkzeug.utils import secure_filename
from datetime import datetime
from models import db,PdfDocument, Member
import magic
import fitz
from flask_jwt_extended import jwt_required, get_jwt_identity
from decorator import analyst_required
from views.summary import generate_and_spend_summary, generate_and_received_summary
from views.extract import (
    extract_transactions,
    extract_metadata,
    extract_summary_table,
    extract_pdf_properties,
    is_valid_mpesa_document
)

upload_bp = Blueprint("upload_bp", __name__)


def is_mpesa_statement(pdf_bytes, password=None):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        if doc.is_encrypted:
            if not password or not doc.authenticate(password):
                return False

        # Read the first 2 pages
        text = ""
        for i in range(min(2, len(doc))):
            page = doc.load_page(i)
            text += page.get_text().lower()

        required_keywords = [
            "m-pesa statement",
            "safaricom",
            "receipt no",
            "completion time",
            "details",
            "transaction status",
            "paid in",
            "withdrawn",
            "balance"
        ]

        return all(keyword in text for keyword in required_keywords)
    except Exception:
        return False



@upload_bp.route('/upload', methods=['POST'])
@jwt_required()
@analyst_required
def upload_pdf():
    # Verify  privileges
    current_user_id = get_jwt_identity()
    analyst = Member.query.get(current_user_id)
    if not analyst or not analyst.is_analyst:
        return jsonify({"error": "Data Analyst privileges required"}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "File must be a PDF"}), 400

    password = request.form.get('password', '').strip() or None

    try:
        pdf_bytes = file.read()
        filename = secure_filename(file.filename)

        # MIME type check
        mime = magic.from_buffer(pdf_bytes, mime=True)
        if mime != 'application/pdf':
            return jsonify({"error": "Uploaded file is not a valid PDF"}), 400

        pdf_properties = extract_pdf_properties(pdf_bytes, password)

        if not is_valid_mpesa_document(pdf_properties):
            return jsonify({"error": "The uploaded PDF does not meet required M-PESA statement properties."}), 400

        try:
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        except Exception:
            return jsonify({"error": "Invalid or corrupted PDF file."}), 400

        if not is_mpesa_statement(pdf_bytes, password):
            return jsonify({"error": "This PDF does not appear to be a valid M-PESA statement."}), 400

        #  Save the file metadata to DB
        new_doc = PdfDocument(
            filename=filename,
            content=pdf_bytes,
            uploaded_at=datetime.utcnow()
        )
        db.session.add(new_doc)
        db.session.commit()

        pdf_id = new_doc.id

        # Extract data
        transactions_data = extract_transactions(pdf_bytes, password)
        metadata = extract_metadata(pdf_bytes, password)
        summary_table = extract_summary_table(pdf_bytes, password)

        # Generate and save summaries (persist + return dicts)
        spending_money_summary = generate_and_spend_summary(transactions_data, pdf_id)
        received_money_summary = generate_and_received_summary(transactions_data, pdf_id)


        return jsonify({
            "success": "Uploaded and analyzed successfully",
            "filename": filename,
            "metadata": metadata,
            "summary_table": summary_table,
            "spending_money_summary": spending_money_summary,
            "received_money_summary":  received_money_summary,
            "transactions": transactions_data,
        }), 200

    except Exception as e:
        print("ERROR during upload:", e)
        return jsonify({"error": str(e)}), 500