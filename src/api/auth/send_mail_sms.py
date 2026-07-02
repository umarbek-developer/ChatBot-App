from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_otp_email(user_email, otp_code, otp_type='otp'):
    # 1. HTML tarkibni render qilish
    if otp_type == "otp":
        context = {'code': otp_code}
        html_message = render_to_string('verify_email.html', context)
    else:
        context = {'link': otp_code}
        html_message = render_to_string('verify_email_link.html', context)
    # 2. Plain text varianti (HTML qo'llab-quvvatlamaydigan pochta xizmatlari uchun)
    plain_message = strip_tags(html_message)
    subject = f"Tasdiqlash kodi"
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
    except Exception as e:
        print("error", e)
