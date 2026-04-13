try:
    import qrcode
except ImportError:
    qrcode = None

import io
import base64
from flask import url_for


def generate_upi_qr_code(upi_id, amount, order_id):
    """
    Generate UPI QR code for payment
    """
    # UPI payment string format - use a real UPI ID or your actual business UPI
    upi_string = f"upi://pay?pa=9876543210@ybl&pn=Campus%20Krishi&am={amount}&cu=INR&tn=Order%20{order_id}"

    if qrcode is None:
        # Fallback when qrcode package is missing (offline environment)
        placeholder = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAE0lEQVR42mP8z/C/HwAEgwJ/lT7dZgAAAABJRU5ErkJggg=='
        return {
            'qr_code': placeholder,
            'upi_string': upi_string,
            'upi_id': '9876543210@ybl'
        }

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_string)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64 for embedding in HTML
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_str = base64.b64encode(img_buffer.getvalue()).decode()

    return {
        'qr_code': img_str,
        'upi_string': upi_string,
        'upi_id': '9876543210@ybl'  # Real UPI ID for testing
    }

def generate_payment_qr_code(order_id, total_amount):
    """
    Generate QR code for order payment
    """
    # Use a real UPI ID for testing - replace with your actual business UPI
    return generate_upi_qr_code('9876543210@ybl', total_amount, order_id)
