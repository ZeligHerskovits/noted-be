import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_env_debug_info():
    """Get debug information about environment variables"""
    debug_info = []
    debug_info.append("=== DEBUG: Environment Variables ===")
    debug_info.append(f"DATABASE_URL: {os.getenv('DATABASE_URL')[:50] + '...' if os.getenv('DATABASE_URL') else 'NOT SET'}")
    debug_info.append(f"SECRET_KEY: {os.getenv('SECRET_KEY')[:10] + '...' if os.getenv('SECRET_KEY') else 'NOT SET'}")
    debug_info.append(f"ALGORITHM: {os.getenv('ALGORITHM')}")
    debug_info.append(f"SMTP_SERVER: {os.getenv('SMTP_SERVER')}")
    debug_info.append(f"SMTP_PORT: {os.getenv('SMTP_PORT')}")
    debug_info.append(f"SMTP_USERNAME: {os.getenv('SMTP_USERNAME')}")
    debug_info.append(f"SMTP_PASSWORD: {os.getenv('SMTP_PASSWORD')[:10] + '...' if os.getenv('SMTP_PASSWORD') else 'NOT SET'}")
    debug_info.append(f"FROM_EMAIL: {os.getenv('FROM_EMAIL')}")
    debug_info.append(f"FRONTEND_URL: {os.getenv('FRONTEND_URL')}")
    debug_info.append(f"ENV: {os.getenv('ENV')}")
    debug_info.append(f"AWS_ACCESS_KEY_ID: {os.getenv('AWS_ACCESS_KEY_ID')[:10] + '...' if os.getenv('AWS_ACCESS_KEY_ID') else 'NOT SET'}")
    debug_info.append(f"AWS_SECRET_ACCESS_KEY: {os.getenv('AWS_SECRET_ACCESS_KEY')[:10] + '...' if os.getenv('AWS_SECRET_ACCESS_KEY') else 'NOT SET'}")
    debug_info.append(f"AWS_REGION: {os.getenv('AWS_REGION')}")
    debug_info.append(f"S3_BUCKET_NAME: {os.getenv('S3_BUCKET_NAME')}")
    debug_info.append(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')[:10] + '...' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")
    debug_info.append("=== END DEBUG ===")
    return "\n".join(debug_info)

def send_email(subject, body, to_email):
    """Send email using SMTP settings from environment variables"""
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL")
    
    if not all([smtp_server, smtp_username, smtp_password, from_email]):
        print("❌ Missing SMTP configuration. Cannot send email.")
        print("Required: SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, FROM_EMAIL")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Add body
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()
        
        print(f"✅ Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        return False

if __name__ == "__main__":
    # Get debug info
    debug_info = get_env_debug_info()
    
    # Print to console
    print(debug_info)
    
    # Use your email address directly
    to_email = "zeligh@objectif.solutions"
    
    # Send email
    subject = "Environment Variables Debug Info - Noted Backend"
    send_email(subject, debug_info, to_email) 