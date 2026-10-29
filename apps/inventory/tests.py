from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from core.models import ShopSetting
from products.models import Category, Product

from .models import InventoryMovement, MovementType
from .services import adjust_stock_to_count, get_stock_quantity, record_movement


class InventoryServiceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='stock_owner', password='test-password', role=UserRole.OWNER
		)
		self.category = Category.objects.create(name='قطع اختبار المخزون')
		self.product = Product.objects.create(
			category=self.category,
			name='مصباح اختبار',
			sku='STOCK-00001',
			barcode='200000009999',
			cost_price=Decimal('50.00'),
			sale_price=Decimal('100.00'),
		)
		ShopSetting.objects.create(name='البراق')

	def add_initial_stock(self, quantity=10):
		return record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.INITIAL,
			quantity_delta=quantity,
			actor=self.owner,
			unit_cost=Decimal('50.00'),
			notes='رصيد افتتاحي للاختبار',
		)

	def test_balance_is_derived_from_movements(self):
		self.add_initial_stock(10)
		movement = record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.SALE,
			quantity_delta=-3,
			actor=self.owner,
			notes='بيع تجريبي',
		)
		self.assertEqual(get_stock_quantity(self.product), 7)
		self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 2)
		audit = AuditLog.objects.get(model_name='InventoryMovement', object_id=str(movement.pk))
		self.assertEqual(audit.user, self.owner)
		self.assertEqual(audit.before_values['stock_quantity'], 10)
		self.assertEqual(audit.after_values['stock_quantity'], 7)

	def test_initial_stock_is_recorded_in_audit_log(self):
		movement = self.add_initial_stock(3)
		audit = AuditLog.objects.get(model_name='InventoryMovement', object_id=str(movement.pk))
		self.assertEqual(audit.action, AuditAction.STOCK_ADJUST)
		self.assertEqual(audit.notes, 'رصيد افتتاحي للاختبار')

	def test_cannot_issue_more_than_available_stock_by_default(self):
		self.add_initial_stock(4)
		with self.assertRaises(ValidationError):
			record_movement(
				product_id=self.product.pk,
				movement_type=MovementType.SALE,
				quantity_delta=-5,
				actor=self.owner,
			)
		self.assertEqual(get_stock_quantity(self.product), 4)
		self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 1)

	def test_movement_sign_must_match_movement_type(self):
		with self.assertRaises(ValidationError):
			record_movement(
				product_id=self.product.pk,
				movement_type=MovementType.SALE,
				quantity_delta=2,
				actor=self.owner,
			)

	def test_fractional_quantities_are_rejected_instead_of_truncated(self):
		with self.assertRaises(ValidationError):
			record_movement(
				product_id=self.product.pk,
				movement_type=MovementType.INITIAL,
				quantity_delta=Decimal('1.5'),
				actor=self.owner,
			)

	def test_adjustment_records_only_the_count_difference(self):
		self.add_initial_stock(10)
		movement = adjust_stock_to_count(
			product_id=self.product.pk,
			counted_quantity=7,
			actor=self.owner,
			notes='مطابقة الجرد الفعلي',
			reference='COUNT-001',
		)
		self.assertEqual(movement.movement_type, MovementType.ADJUSTMENT)
		self.assertEqual(movement.quantity, -3)
		self.assertEqual(get_stock_quantity(self.product), 7)

	def test_initial_balance_is_allowed_only_before_other_movements(self):
		self.add_initial_stock(2)
		with self.assertRaises(ValidationError):
			self.add_initial_stock(3)
		self.assertEqual(InventoryMovement.objects.filter(product=self.product).count(), 1)

	def test_negative_stock_requires_shop_setting(self):
		setting = ShopSetting.objects.get()
		setting.allow_negative_stock = True
		setting.save(update_fields=['allow_negative_stock'])
		movement = record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.SALE,
			quantity_delta=-2,
			actor=self.owner,
			notes='تجاوز مصرح به',
		)
		self.assertEqual(movement.quantity, -2)
		self.assertEqual(get_stock_quantity(self.product), -2)
		audit = AuditLog.objects.get(model_name='InventoryMovement', object_id=str(movement.pk))
		self.assertEqual(audit.notes, 'تجاوز مصرح به')
		self.assertEqual(audit.after_values['stock_quantity'], -2)

	def test_negative_stock_override_requires_a_reason(self):
		setting = ShopSetting.objects.get()
		setting.allow_negative_stock = True
		setting.save(update_fields=['allow_negative_stock'])
		with self.assertRaises(ValidationError):
			record_movement(
				product_id=self.product.pk,
				movement_type=MovementType.SALE,
				quantity_delta=-1,
				actor=self.owner,
			)


class InventoryViewTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='inventory_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='inventory_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.clerk = User.objects.create_user(
			username='inventory_clerk', password='test-password', role=UserRole.INVENTORY_CLERK
		)
		self.category = Category.objects.create(name='تصنيف اختبار')
		self.product = Product.objects.create(
			category=self.category,
			name='منتج للمخزون',
			sku='STOCK-00002',
			barcode='200000009998',
			cost_price=Decimal('25.00'),
			sale_price=Decimal('40.00'),
		)
		ShopSetting.objects.create(name='البراق')

	def test_inventory_pages_are_forbidden_to_cashier(self):
		self.client.force_login(self.cashier)
		response = self.client.get(reverse('inventory_stock_list'))
		self.assertEqual(response.status_code, 403)

	def test_inventory_clerk_can_view_stock_list(self):
		self.client.force_login(self.clerk)
		response = self.client.get(reverse('inventory_stock_list'))
		self.assertEqual(response.status_code, 200)

	def test_inventory_clerk_cannot_enter_initial_balance(self):
		self.client.force_login(self.clerk)
		response = self.client.post(
			reverse('inventory_movement_create'),
			{
				'product': self.product.pk,
				'movement_type': MovementType.INITIAL,
				'quantity': 5,
				'notes': 'محاولة غير مصرح بها',
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertFalse(InventoryMovement.objects.exists())

	def test_owner_can_record_initial_balance_through_form(self):
		self.client.force_login(self.owner)
		response = self.client.post(
			reverse('inventory_movement_create'),
			{
				'product': self.product.pk,
				'movement_type': MovementType.INITIAL,
				'quantity': 5,
				'unit_cost': '25.00',
				'notes': 'رصيد افتتاحي',
			},
		)
		self.assertRedirects(
			response,
			reverse('inventory_product_history', args=[self.product.pk]),
		)
		self.assertEqual(get_stock_quantity(self.product), 5)
