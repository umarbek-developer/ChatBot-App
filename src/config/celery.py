# config/celery.py (yoki src/celery.py)
import os
from celery import Celery

# Django sozlamalari faylini Celery-ga tanishtiramiz.
# 'config.settings' paketi DEBUG qiymatiga qarab development/production ni tanlaydi
# (config.settings.base emas — aks holda prod sozlamalari e'tiborga olinmaydi).
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Celery ilovasini yaratamiz (loyiha nomini xohlagancha yozish mumkin)
app = Celery('ziyodev_django_project')

# Barcha Celery sozlamalarini Django settings.py ichidan 'CELERY_' prefiksi orqali o'qiydi
app.config_from_object('django.conf:settings', namespace='CELERY')

# Loyihadagi barcha tasks.py fayllarini avtomatik qidirib topadi
app.autodiscover_tasks()