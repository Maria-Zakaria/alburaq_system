from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, UserRole

class RBACPermissionsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # مدير النظام / المالك
        self.owner = User.objects.create_user(
            username='owner_user',
            password='password123',
            role=UserRole.OWNER
        )
        # كاشير
        self.cashier = User.objects.create_user(
            username='cashier_user',
            password='password123',
            role=UserRole.CASHIER
        )

    def test_owner_can_access_user_list(self):
        """التحقق من أن المالك يستطيع الوصول لصفحة إدارة المستخدمين"""
        self.client.login(username='owner_user', password='password123')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)

    def test_cashier_forbidden_from_user_list(self):
        """التحقق الخادمي SERVER-SIDE من أن الكاشير يُمنع من الوصول لصفحة المستخدمين (403)"""
        self.client.login(username='cashier_user', password='password123')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)
