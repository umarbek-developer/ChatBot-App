import uuid
import random
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.utils import timezone



class CustomUserManager(BaseUserManager):

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user
    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)



class User(AbstractUser):
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True)
    email = models.EmailField(unique=True, max_length=50)
    telegram_id = models.CharField(max_length=50, null=True, blank=True)
    phone_number = models.CharField(max_length=13, null=True, blank=True)
    language = models.CharField(max_length=2, default='uz')
    is_active = models.BooleanField(default=False)
    username = None
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name']

    objects = CustomUserManager()

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def __str__(self):
        return self.full_name

    def token(self):
        refresh = RefreshToken.for_user(self)
        return {
            'refresh_token': str(refresh),
            'access_token': str(refresh.access_token),
        }

    def check_hash_password(self):
        if not self.password.startswith('pbkdf2_sha256'):
            self.set_password(self.password)

    def check_empty_password(self):
        if not self.username:
            username = f'username-{uuid.uuid4().__str__().split("-")[-1]}'
            
        if not self.password:
            password = f'password-{uuid.uuid4().__str__().split("-")[-1]}'
            self.password = password


    def save(self, *args, **kwargs):
        self.check_empty_password()
        self.check_hash_password()
        super(User, self).save(*args, **kwargs)


class UserOTPVerifications(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    expired_at = models.DateTimeField()
    attapts = models.IntegerField(default=0)
    for_forget_password = models.BooleanField(default=False)
    for_forget_password_verified = models.BooleanField(default=False)
    resend_attapts = models.IntegerField(default=0)
    error_expired_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} | {self.code}"
        
    def generate_code(self):
        otp = random.randint(100000, 999999)
        now = timezone.now()
        next_time = now + timedelta(minutes=3)
        self.expired_at = next_time
        self.code = otp
        self.save()
        return otp
    
    def is_code_expired(self):
        if self.expired_at >= timezone.now():
            return self.expired_at.timestamp()
        return False
    

class UserOTPIDVerifications(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.UUIDField(default=uuid.uuid4)
    expired_at = models.DateTimeField()
    attapts = models.IntegerField(default=0)
    error_expired_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} | {self.code}"
    
    def is_code_expired(self):
        if self.expired_at >= timezone.now():
            return self.expired_at.timestamp()
        return False
    

class ChangePasswordLogs(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    old_password = models.CharField(max_length=255)
    new_password = models.CharField(max_length=255)
    expired_at = models.DateTimeField()
    attapts = models.IntegerField(default=0)
    error_expired_at = models.DateTimeField()
    is_changed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} | {self.attapts}"
    
    def is_expired(self):
        if self.expired_at >= timezone.now():
            return self.expired_at
        return False
    
    def is_blocked(self):
        if self.error_expired_at >= timezone.now():
            return self.error_expired_at
        return False
    

class ChangeEmailLogs(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    old_email = models.CharField(max_length=150, default="")
    new_email = models.CharField(max_length=150, default="")
    expired_at = models.DateTimeField()
    attapts = models.IntegerField(default=0)
    resend_attapts = models.IntegerField(default=0)
    error_expired_at = models.DateTimeField()
    is_changed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} | {self.attapts}"
    
    def is_expired(self):
        if self.expired_at >= timezone.now():
            return self.expired_at
        return False

    def generate_code(self):
        otp = random.randint(100000, 999999)
        now = timezone.now()
        next_time = now + timedelta(minutes=3)
        self.expired_at = next_time
        self.code = otp
        self.save()
        return otp

    def is_blocked(self):
        if self.error_expired_at >= timezone.now():
            return self.error_expired_at
        return False