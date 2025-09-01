from flask import Flask, request, jsonify, Blueprint
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from collections import defaultdict
from sqlalchemy import func
import re
import fitz
from collections import defaultdict
import tempfile

extract_bp = Blueprint("extract_bp", __name__)

# Known metadata properties from real Safaricom M-PESA statement(s)
KNOWN_MPESA_PROPERTIES = [
    {
        "subject": "M-PESA Statement",
        "author": "Safaricom PLC",
        "keywords": "M-PESA,Statement",
        "producer": "OpenPDF 1.3.26",
        "creator": "Safaricom PLC",
        "format": "PDF-1.7"
    },
]


def calculate_duration_months(period_str):
    if " - " in period_str:
        parts = [p.strip() for p in period_str.split(" - ")]
        if len(parts) == 2:
            try:
                from_date = datetime.strptime(parts[0], "%d %b %Y")
                to_date = datetime.strptime(parts[1], "%d %b %Y")

                months = (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month)
                if to_date.day < from_date.day:
                    months -= 1

                return max(months, 0)
            except ValueError as e:
                raise ValueError(f"Failed to parse dates in period: {period_str} — {e}")
    return 0


def extract_metadata(pdf_bytes, password=None):
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    if doc.is_encrypted:
        if not password or not doc.authenticate(password):
            raise Exception("PDF decryption failed")

    first_page_text = doc[0].get_text()
    last_page_text = doc[-1].get_text()

    # Extract metadata
    name_match = re.search(r"Customer Name\s*:\s*(.*)", first_page_text)
    phone_match = re.search(r"Mobile Number\s*:\s*(.*)", first_page_text)
    email_match = re.search(r"Email Address\s*:\s*(.*)", first_page_text)
    period_match = re.search(r"Statement Period\s*:\s*(.*)", first_page_text)
    date_match = re.search(r"Request Date\s*:\s*(.*)", first_page_text)

    # Extract raw values
    customer_name = name_match.group(1).strip() if name_match else "Unknown"
    mobile_number = phone_match.group(1).strip() if phone_match else "Unknown"
    email_address = email_match.group(1).strip() if email_match else "Unknown"
    statement_period = period_match.group(1).strip() if period_match else "Unknown"
    request_date = date_match.group(1).strip() if date_match else "Unknown"
    duration_months = calculate_duration_months(statement_period) if statement_period != "Unknown" else None

    
    return {
        "customer_name": customer_name,
        "mobile_number": mobile_number,
        "email_address": email_address,
        "statement_period": statement_period,
        "request_date": request_date,
        "statement_duration_months": duration_months
    }

def clean_amount(value):
    try:
        if value in ["", "-", None]:
            return 0.0
        return float(value.replace(",", "").strip())
    except Exception:
        return 0.0



def extract_summary_table(pdf_bytes, password=None):
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    if doc.is_encrypted:
        if not password or not doc.authenticate(password):
            raise Exception("PDF decryption failed")

    page = doc[0]  # Only check page 1
    blocks = page.get_text("blocks")
    summary_data = []

    header_y = None
    detailed_y = None

    for block in blocks:
        text = block[4].lower()
        if "transaction type" in text and "paid in" in text and "paid out" in text:
            header_y = block[1]
            break

    for block in blocks:
        if "detailed statement" in block[4].lower():
            detailed_y = block[1]
            break

    for block in blocks:
        y0 = block[1]
        text = block[4].strip()

        if y0 > header_y and (detailed_y is None or y0 < detailed_y):
            numbers = re.findall(r"\d[\d,]*\.\d{2}", text)
            if len(numbers) >= 2:
                summary_data.append(text)

    summary_result = []
    for line in summary_data:
        numbers = re.findall(r"\d[\d,]*\.\d{2}", line)
        if len(numbers) < 2:
            continue

        transaction_type = re.sub(r"\d[\d,]*\.\d{2}", "", line)
        transaction_type = re.sub(r"\s+", " ", transaction_type.replace(":", "")).strip()
        paid_in = clean_amount(numbers[0])
        paid_out = clean_amount(numbers[1])

        summary_result.append({
            "transaction_type": transaction_type,
            "total_paid_in": paid_in,
            "total_paid_out": paid_out
        })

    return summary_result


def extract_transactions(pdf_bytes, password=None):
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')

    if doc.is_encrypted:
        if not password or not doc.authenticate(password):
            raise Exception("PDF decryption failed")

    transactions = []
    status_keywords = r"^(Completed|Failed|Pending)$"
    receipt_no_pattern = r"^[A-Z0-9]{10,}$"  # Covers receipt numbers like TFP39YYAD3, not just TF

    for page in doc:
        lines = page.get_text().split('\n')
        i = 0
        while i < len(lines):
            # Match receipt number
            if re.match(receipt_no_pattern, lines[i].strip()):
                receipt_no = lines[i].strip()
                i += 1
                if i >= len(lines): break

                completion_time = lines[i].strip()
                i += 1
                if i >= len(lines): break

                # Look ahead for transaction status
                details_lines = []
                status_line_index = None
                for j in range(i, min(i + 7, len(lines))):
                    if re.match(status_keywords, lines[j].strip()):
                        status_line_index = j
                        break

                if status_line_index is None:
                    i += 1
                    continue

                details_lines = lines[i:status_line_index]
                details = "\n".join([d.strip() for d in details_lines])
                transaction_status = lines[status_line_index].strip()
                i = status_line_index + 1

                # Extract amount and balance
                monetary_fields = []
                while i < len(lines) and len(monetary_fields) < 2:
                    line = lines[i].strip()
                    if re.match(r'^-?[\d,]+(\.\d{1,2})?$', line) or line in ["", "-"]:
                        monetary_fields.append(line)
                        i += 1
                    else:
                        break

                amount = clean_amount(monetary_fields[0]) if len(monetary_fields) > 0 else 0.0
                balance = clean_amount(monetary_fields[1]) if len(monetary_fields) > 1 else 0.0

                paid_in = amount if amount > 0 else 0.0
                withdrawn = amount if amount < 0 else 0.0
                transactions.append({
                    "receipt_no": receipt_no,
                    "completion_time": completion_time,
                    "details": details,
                    "transaction_status": transaction_status,
                    "paid_in": paid_in,
                    "withdrawn": withdrawn,
                    "balance": balance
                })

            else:
                i += 1

    return transactions



def extract_pdf_properties(pdf_bytes, password=None):
    def parse_pdf_date(pdf_date):
        try:
            if pdf_date and pdf_date.startswith("D:"):
                dt = datetime.strptime(pdf_date[2:16], "%Y%m%d%H%M%S")
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return "N/A"

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if doc.is_encrypted:
        if not password or not doc.authenticate(password):
            raise Exception("PDF decryption failed")

    info = doc.metadata
    raw_version = doc.xref_get_key(1, "Version")[1]
    format_version = f"PDF-{raw_version.lstrip('/') if raw_version else 'Unknown'}"

    properties = {
        "author": info.get("author", "N/A"),
        "created": parse_pdf_date(info.get("creationDate")),
        "creator": info.get("creator", "N/A"),
        "format": format_version,
        "keywords": info.get("keywords", "N/A"),
        "modified": parse_pdf_date(info.get("modDate")),
        "producer": info.get("producer", "N/A"),
        "subject": info.get("subject", "N/A"),
    }

    return properties


def is_valid_mpesa_document(extracted_props):
    for known in KNOWN_MPESA_PROPERTIES:
        match = all(
            extracted_props.get(key) == value
            for key, value in known.items()
        )
        if match:
            return True
    return False