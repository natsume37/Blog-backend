import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def send_email(email_to: str, subject: str, html_content: str) -> bool:
    """
    发送邮件
    """
    try:
        logger.info(f"Preparing to send email to {email_to}")
        logger.debug(f"SMTP Config: Host={settings.SMTP_HOST}, Port={settings.SMTP_PORT}, User={settings.SMTP_USER}, From={settings.EMAILS_FROM_EMAIL}")

        message = MIMEMultipart()
        
        # 处理发件人名称中的非 ASCII 字符
        from_name = settings.EMAILS_FROM_NAME
        try:
            from_name.encode('ascii')
        except UnicodeEncodeError:
            from_name = Header(from_name, 'utf-8').encode()
            
        message["From"] = formataddr((from_name, settings.EMAILS_FROM_EMAIL))
        message["To"] = formataddr((None, email_to))
        message["Subject"] = Header(subject, "utf-8")

        message.attach(MIMEText(html_content, "html", "utf-8"))

        logger.debug("Connecting to SMTP server...")
        # 使用 SSL 连接
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()  # 启用 TLS
        
        logger.debug("Logging in...")
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        
        logger.debug("Sending mail...")
        server.sendmail(settings.EMAILS_FROM_EMAIL, [email_to], message.as_string())
        server.quit()
        
        logger.info(f"Email sent successfully to {email_to}")
        return True
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logger.error(f"Failed to send email to {email_to}. Error: {e}\nTraceback: {error_msg}")
        print(f"Email Error: {e}")
        print(f"Traceback: {error_msg}")
        return False

def send_reset_password_email(email_to: str, code: str):
    """
    发送重置密码验证码邮件
    """
    subject = f"{settings.EMAILS_FROM_NAME} - 重置密码验证码"
    html_content = f"""
    <html>
        <body>
            <p>您好！</p>
            <p>您正在申请重置密码，您的验证码是：</p>
            <h2 style="color: #409EFF;">{code}</h2>
            <p>验证码有效期为 10 分钟，请勿泄露给他人。</p>
            <p>如果这不是您的操作，请忽略此邮件。</p>
        </body>
    </html>
    """
    return send_email(email_to, subject, html_content)

def send_register_verification_email(email_to: str, code: str):
    """
    发送注册验证码邮件
    """
    subject = f"{settings.APP_NAME} - 注册验证码"
    html_content = f"""
    <html>
        <body>
            <p>您好！</p>
            <p>欢迎注册 {settings.APP_NAME}，您的注册验证码是：</p>
            <h2 style="color: #409EFF;">{code}</h2>
            <p>验证码有效期为 10 分钟，请勿泄露给他人。</p>
            <p>如果这不是您的操作，请忽略此邮件。</p>
        </body>
    </html>
    """
    return send_email(email_to, subject, html_content)
