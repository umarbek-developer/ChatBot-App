import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# Celery loglarini terminalda chiroyli ko'rish uchun loger
logger = logging.getLogger(__name__)

@shared_task(name="send_otp_email_task")
def send_otp_email_task(user_email, otp_code, otp_type='otp'):
    """
    Foydalanuvchiga OTP kod yoki Tasdiqlash havolasini 
    HTML shablon orqali fonda (asinxron) yuboruvchi Celery vazifasi.
    """
    logger.info(f"Email yuborish boshlandi: {user_email} (Turi: {otp_type})")

    # 1. HTML tarkibni render qilish
    try:
        if otp_type == "otp":
            context = {'code': otp_code}
            html_message = render_to_string('verify_email.html', context)
        else:
            context = {'link': otp_code}
            html_message = render_to_string('verify_email_link.html', context)
            
    except Exception as template_error:
        logger.error(f"HTML shablonni render qilishda xatolik: {template_error}")
        raise template_error

    # 2. Plain text varianti (HTML qo'llab-quvvatlamaydigan pochta xizmatlari uchun)
    plain_message = strip_tags(html_message)
    subject = "Tasdiqlash kodi"
    from_email = settings.EMAIL_HOST_USER
    recipient_list = [user_email]

    # 3. Xatni yuborish
    try:
        send_mail(
            subject,
            plain_message,
            from_email,
            recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email muvaffaqiyatli ketdi: {user_email}")
        return f"Email successfully sent to {user_email}"
        
    except Exception as e:
        # Celery ishlayotganda print() loglarda yaxshi chiqmaydi, logger.error ishonchliroq
        logger.error(f"Email yuborishda xatolik yuz berdi ({user_email}): {e}")
        raise e