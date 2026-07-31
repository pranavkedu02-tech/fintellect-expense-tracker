import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================
# Gmail Credentials
# ============================================

EMAIL = "fintellectai01@gmail.com"          # Your Gmail
APP_PASSWORD = "vejh ydrd iyar wobh"

# ============================================
# Receiver
# ============================================

TO_EMAIL = "pranavkedu02@gmail.com"        # Can be same as sender

# ============================================
# Email
# ============================================

message = MIMEMultipart()

message["From"] = EMAIL
message["To"] = TO_EMAIL
message["Subject"] = "FintellectAI Test Email"

body = """
Hello,

This is a test email from FintellectAI Expense Tracker.

If you received this email, SMTP is working successfully.

Regards,
FintellectAI
"""

message.attach(MIMEText(body, "plain"))

try:

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()

    server.login(
        EMAIL,
        APP_PASSWORD
    )

    server.sendmail(
        EMAIL,
        TO_EMAIL,
        message.as_string()
    )

    server.quit()

    print("✅ Email sent successfully!")

except Exception as e:

    print("❌ Error:")
    print(e)