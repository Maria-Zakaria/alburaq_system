from decimal import Decimal
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, UserRole
from products.models import Category, Product
from products.forms import ProductForm
from products.models import Category, Product

class ProductModelTestCase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="إضاءة", is_active=True)
        self.product = Product.objects.create(
            category=self.category,
            name="مصباح LED H7",
            sku="ALB-00001",
            barcode="200000000001",
            cost_price=Decimal("50.00"),
            sale_price=Decimal("100.00"),
            wholesale_price=Decimal("80.00"),
            min_stock_level=5,
        )

    def test_product_created_correctly(self):
        """التحقق من إنشاء المنتج بالبيانات الصحيحة"""
        self.assertEqual(self.product.name, "مصباح LED H7")
        self.assertEqual(self.product.sale_price, Decimal("100.00"))
        self.assertEqual(self.product.category.name, "إضاءة")
        self.assertTrue(self.product.is_active)
        self.assertFalse(self.product.is_published_web)

    def test_product_str(self):
        """التحقق من عرض المنتج نصياً"""
        self.assertIn("مصباح LED H7", str(self.product))

    def test_product_form_rejects_images_over_five_megabytes(self):
        form = ProductForm()
        form.cleaned_data = {'image': SimpleNamespace(size=5 * 1024 * 1024 + 1)}
        with self.assertRaises(ValidationError):
            form.clean_image()

    def test_barcode_unique(self):
        """التحقق من أن الباركود فريد"""
        with self.assertRaises(Exception):
            Product.objects.create(
                category=self.category,
                name="منتج مكرر",
                sku="ALB-00099",
                barcode="200000000001",  # نفس الباركود
                cost_price=10.00,
                sale_price=20.00,
            )

class ProductViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(
            username='owner_test', password='password123', role=UserRole.OWNER
        )
        self.cashier = User.objects.create_user(
            username='cashier_test', password='password123', role=UserRole.CASHIER
        )
        self.inventory_clerk = User.objects.create_user(
            username='inventory_test', password='password123', role=UserRole.INVENTORY_CLERK
        )
        self.category = Category.objects.create(name="شاشات", is_active=True)
        self.product = Product.objects.create(
            category=self.category,
            name="شاشة سيارة 9 بوصة",
            sku="ALB-00002",
            barcode="200000000002",
            cost_price=Decimal("300.00"),
            sale_price=Decimal("500.00"),
            min_stock_level=2,
        )

    def test_product_list_accessible_by_owner(self):
        """المدير يصل لقائمة المنتجات"""
        self.client.login(username='owner_test', password='password123')
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)

    def test_product_list_accessible_by_cashier(self):
        """الكاشير يستطيع رؤية دليل المنتجات (للبحث والبيع)"""
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 200)

    def test_product_create_blocked_for_cashier(self):
        """الكاشير لا يستطيع إضافة منتج جديد — محمي بـ SERVER-SIDE"""
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get(reverse('product_create'))
        self.assertEqual(response.status_code, 403)

    def test_inventory_clerk_cannot_create_or_update_products(self):
        self.client.login(username='inventory_test', password='password123')
        create_response = self.client.get(reverse('product_create'))
        update_response = self.client.get(reverse('product_update', args=[self.product.pk]))
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)

    def test_inventory_clerk_cannot_view_product_cost(self):
        self.client.login(username='inventory_test', password='password123')
        list_response = self.client.get(reverse('product_list'))
        detail_response = self.client.get(reverse('product_detail', args=[self.product.pk]))
        self.assertNotContains(list_response, '300.00')
        self.assertNotContains(detail_response, '300.00')

    def test_barcode_api_returns_product(self):
        """التحقق من أن API الباركود تُعيد بيانات المنتج بشكل صحيح"""
        self.client.login(username='owner_test', password='password123')
        response = self.client.get(reverse('api_search_barcode'), {'code': '200000000002'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], "شاشة سيارة 9 بوصة")

    def test_barcode_api_not_found(self):
        """التحقق من أن API الباركود تُعيد 404 للباركود غير الموجود"""
        self.client.login(username='owner_test', password='password123')
        response = self.client.get(reverse('api_search_barcode'), {'code': '9999999999'})
        self.assertEqual(response.status_code, 404)

    def test_category_list_blocked_for_cashier(self):
        self.client.login(username='cashier_test', password='password123')
        response = self.client.get(reverse('category_list'))
        self.assertEqual(response.status_code, 403)

    def test_owner_can_update_category(self):
        self.client.login(username='owner_test', password='password123')
        response = self.client.post(
            reverse('category_update', args=[self.category.pk]),
            {'name': 'شاشات وكاميرات', 'description': 'منتجات العرض', 'is_active': 'on'},
        )
        self.assertRedirects(response, reverse('category_list'))
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'شاشات وكاميرات')
        self.assertEqual(self.category.description, 'منتجات العرض')

    def test_owner_can_disable_category_without_deleting_it(self):
        self.client.login(username='owner_test', password='password123')
        response = self.client.post(reverse('category_toggle_active', args=[self.category.pk]))
        self.assertRedirects(response, reverse('category_list'))
        self.category.refresh_from_db()
        self.assertFalse(self.category.is_active)
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_cashier_cannot_disable_category(self):
        self.client.login(username='cashier_test', password='password123')
        response = self.client.post(reverse('category_toggle_active', args=[self.category.pk]))
        self.assertEqual(response.status_code, 403)
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_active)

    def test_product_publication_change_requires_post(self):
        self.client.login(username='owner_test', password='password123')
        response = self.client.get(reverse('product_toggle_web', args=[self.product.pk]))
        self.assertEqual(response.status_code, 405)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_published_web)

    def test_cashier_cannot_change_product_publication(self):
        self.client.login(username='cashier_test', password='password123')
        response = self.client.post(reverse('product_toggle_web', args=[self.product.pk]))
        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_published_web)

    def test_owner_can_change_product_publication(self):
        self.client.login(username='owner_test', password='password123')
        response = self.client.post(reverse('product_toggle_web', args=[self.product.pk]))
        self.assertRedirects(response, reverse('product_detail', args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_published_web)
