from rest_framework import serializers
from apps.users.models import User
from rest_framework.exceptions import ValidationError


class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password']

    def validate_first_name(self, obj : str):
        if len(obj) < 2:
            raise ValidationError("First name must be length more 5")
        elif len(obj) > 150:
            raise ValidationError("your first name must be length less 150")
        return obj


    def validate_last_name(self, obj : str):
        if obj:
            if len(obj) > 150:
                raise ValidationError("your last_name must be length less 150")
        return obj
    

    def validate_password(self, password : str):
        symbles = ['!', "@", "#", "$", "%", "^", "&", "*", "(", ")", "?", ",", ".", "_", "-", "=", "[", "]", '"', "'", ":", ";"]
        if len(password) < 8:
            raise ValidationError("your password must be length more 8")
        elif len(password) > 35:
            raise ValidationError("your password must be length less 35")
        elif not any(char.isupper() for char in password):
            raise ValidationError("your password must contain capital letter")
        elif not any(char.isdigit() for char in password):
            raise ValidationError("your password must contain numbers")
        elif not any(char.islower() for char in password):
            raise ValidationError("your password must contain lower letter")
        elif not any(char in symbles for char in password):
            raise ValidationError("your password must contain symbles")
        return password
    
    
class UserLoginSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']


class UserLoginSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']
