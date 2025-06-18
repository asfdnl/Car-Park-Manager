import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Microsoft 365 SMTP configuration
SMTP_SERVER = 'smtp.office365.com'
SMTP_PORT = 587
SENDER_EMAIL = 'mfedoc@mfeformwork.com'
SENDER_PASSWORD = 'Abcd@123456'

def send_email_notification(receiver_email, owner_name, license_plate, location):
    """
    Sends an email notification to the vehicle owner via Microsoft 365 SMTP.
    
    Args:
        receiver_email (str): Owner's email address
        owner_name (str): Owner's name
        license_plate (str): Vehicle license plate
        location (str): Office location or parking location
    
    Returns:
        (bool, str): Tuple with success flag and message
    """

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Action Required: Kindly Repark Your Vehicle ({license_plate})"
        msg['From'] = SENDER_EMAIL
        msg['To'] = receiver_email

        html_content = f"""
        <html>
        <body>
            <p>Dear {owner_name},</p>
            <p>Your vehicle with license plate <strong>{license_plate}</strong> is currently blocking the road/area.</p>
            <p>Please repark your vehicle as soon as possible to avoid inconvenience.</p>
            <p>Thank you for your prompt action.
            <p>=====================================================================================================================================================================================================================================================</p>
            <p><em>Disclaimer: This is an automated message, please do not reply.</em></p>
        </body>
        </html>
        """

        part = MIMEText(html_content, 'html')
        msg.attach(part)

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()

        return True, "Email sent successfully."

    except Exception as e:
        return False, str(e)
