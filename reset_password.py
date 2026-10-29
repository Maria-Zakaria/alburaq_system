import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alburaq_core.settings')

import django
django.setup()

from accounts.models import User

# حذف وإعادة إنشاء المستخدم admin إن لزم
try:
    u = User.objects.get(username='admin')
    u.set_password('admin123')
    u.is_active = True
    u.is_staff = True
    u.is_superuser = True
    u.role = 'OWNER'
    u.save()
    print(f"[OK] Password reset for user: {u.username}")
    print(f"     role={u.role}, active={u.is_active}, superuser={u.is_superuser}")
except User.DoesNotExist:
    u = User.objects.create_superuser(
        username='admin',
        password='admin123',
        role='OWNER',
    )
    print(f"[CREATED] New superuser: {u.username}")

# تحقق من تسجيل الدخول
from django.contrib.auth import authenticate
user = authenticate(username='admin', password='admin123')
if user:
    print(f"[AUTH TEST] Login works for: {user.username}")
else:
    print("[AUTH TEST] FAILED - login did not work!")

