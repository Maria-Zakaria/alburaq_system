import json
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift
from core.models import ShopSetting
from customers.models import Customer
from inventory.models import InventoryMovement, MovementType
from inventory.services import get_stock_quantity, record_movement
from payments.models import FinancialTransaction, TransactionType
from products.models import Category, Product

from .models import PaymentMethod, SaleInvoice, SaleItem, SaleStatus
from .services import create_sale


class SaleServiceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='sale_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='sale_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.supervisor = User.objects.create_user(
			username='sale_supervisor', password='test-password', role=UserRole.SHIFT_SUPERVISOR
		)
		self.customer = Customer.objects.create(name='عميل البيع')
		category = Category.objects.create(name='تصنيف اختبار البيع')
		self.product = Product.objects.create(
			category=category,
			name='منتج POS',
			sku='POS-00001',
			barcode='200000007777',
			cost_price=Decimal('50.00'),
			sale_price=Decimal('100.00'),
		)
		ShopSetting.objects.create(name='البراق')
		record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.INITIAL,
			quantity_delta=10,
			unit_cost=Decimal('50.00'),
			actor=self.owner,
			notes='رصيد اختبار البيع',
		)

	def test_sale_saves_historical_price_cost_and_stock_atomically(self):
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 2}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '200.00'}],
			actor=self.cashier,
		)
		item = invoice.items.get()
		self.assertEqual(invoice.status, SaleStatus.COMPLETED)
		self.assertEqual(item.historical_sale_price, Decimal('100.00'))
		self.assertEqual(item.historical_cost_price, Decimal('50.00'))
		self.assertEqual(item.total_price, Decimal('200.00'))
		self.assertEqual(get_stock_quantity(self.product), 8)
		movement = InventoryMovement.objects.get(reference=invoice.invoice_number)
		self.assertEqual(movement.quantity, -2)
		self.assertEqual(movement.unit_cost, Decimal('50.00'))
		self.product.sale_price = Decimal('125.00')
		self.product.cost_price = Decimal('60.00')
		self.product.save(update_fields=['sale_price', 'cost_price'])
		item.refresh_from_db()
		self.assertEqual(item.historical_sale_price, Decimal('100.00'))
		self.assertEqual(item.historical_cost_price, Decimal('50.00'))

	def test_repeated_request_key_returns_same_invoice_without_double_stock_issue(self):
		request_key = uuid4()
		payload = {
			'lines': [{'product_id': self.product.pk, 'quantity': 1}],
			'tenders': [{'method': 'CARD_NETWORK', 'amount': '100.00'}],
			'actor': self.cashier,
			'idempotency_key': request_key,
		}
		first_invoice = create_sale(**payload)
		retry_invoice = create_sale(**payload)
		self.assertEqual(retry_invoice.pk, first_invoice.pk)
		self.assertEqual(SaleInvoice.objects.count(), 1)
		self.assertEqual(FinancialTransaction.objects.count(), 1)
		self.assertEqual(get_stock_quantity(self.product), 9)

	def test_moving_weighted_average_cost_is_saved_at_sale_time(self):
		record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.PURCHASE,
			quantity_delta=10,
			unit_cost=Decimal('100.00'),
			actor=self.owner,
			notes='شراء اختبار لتكلفة المتوسط',
		)
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '100.00'}],
			actor=self.cashier,
		)
		self.assertEqual(invoice.items.get().historical_cost_price, Decimal('75.00'))

	def test_service_and_product_can_be_sold_on_one_invoice(self):
		invoice = create_sale(
			lines=[
				{'product_id': self.product.pk, 'quantity': 1},
				{'service_name': 'تركيب إضاءة', 'unit_price': '25.00', 'quantity': 1},
			],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '125.00'}],
			actor=self.cashier,
		)
		product_line = invoice.items.get(product=self.product)
		service_line = invoice.items.get(product__isnull=True)
		self.assertEqual(invoice.total_amount, Decimal('125.00'))
		self.assertEqual(get_stock_quantity(self.product), 9)
		self.assertEqual(service_line.service_name, 'تركيب إضاءة')
		self.assertEqual(service_line.historical_cost_price, Decimal('0.00'))
		self.assertEqual(
			InventoryMovement.objects.filter(reference=invoice.invoice_number).count(),
			1,
		)

	def test_mixed_payment_cash_change_and_customer_debt_are_traceable(self):
		shift = CashShift.objects.create(cashier=self.cashier, opening_balance=Decimal('100.00'))
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[
				{'method': 'CASH', 'amount': '40.00'},
				{'method': 'CARD_NETWORK', 'amount': '30.00', 'reference': 'CARD-45'},
			],
			cash_received='50.00',
			customer_id=self.customer.pk,
			actor=self.cashier,
		)
		invoice.refresh_from_db()
		self.assertEqual(invoice.payment_method, PaymentMethod.MIXED)
		self.assertEqual(invoice.paid_amount, Decimal('70.00'))
		self.assertEqual(invoice.remaining_amount, Decimal('30.00'))
		self.assertEqual(invoice.change_given, Decimal('10.00'))
		payments = FinancialTransaction.objects.filter(sale_invoice=invoice)
		self.assertEqual(payments.count(), 2)
		self.assertEqual(payments.get(payment_method='CASH').shift, shift)
		self.assertEqual(payments.get(reference='CARD-45').amount, Decimal('30.00'))
		self.assertEqual(self.customer.outstanding_balance, Decimal('30.00'))
		self.assertTrue(AuditLog.objects.filter(
			model_name='SaleInvoice', object_id=str(invoice.pk), action=AuditAction.CREATE
		).exists())

	def test_full_credit_requires_customer(self):
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 1}],
				actor=self.cashier,
			)
		self.assertFalse(SaleInvoice.objects.exists())
		self.assertEqual(get_stock_quantity(self.product), 10)

	def test_overpayment_and_duplicate_cash_tenders_are_rejected(self):
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 1}],
				tenders=[{'method': 'CARD_NETWORK', 'amount': '101.00'}],
				actor=self.cashier,
			)
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 1}],
				tenders=[
					{'method': 'CASH', 'amount': '20.00'},
					{'method': 'CASH', 'amount': '20.00'},
				],
				actor=self.cashier,
			)
		self.assertFalse(SaleInvoice.objects.exists())

	def test_cash_tender_requires_exactly_one_open_shift(self):
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 1}],
				tenders=[{'method': 'CASH', 'amount': '100.00'}],
				actor=self.cashier,
			)
		self.assertFalse(SaleInvoice.objects.exists())
		CashShift.objects.create(cashier=self.cashier, opening_balance=Decimal('0.00'))
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[{'method': 'CASH', 'amount': '100.00'}],
			actor=self.cashier,
		)
		self.assertIsNotNone(invoice.shift_id)

	def test_insufficient_stock_rolls_back_invoice_payment_and_movement(self):
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 11}],
				tenders=[{'method': 'CARD_NETWORK', 'amount': '1100.00'}],
				actor=self.cashier,
			)
		self.assertFalse(SaleInvoice.objects.exists())
		self.assertFalse(FinancialTransaction.objects.exists())
		self.assertEqual(get_stock_quantity(self.product), 10)

	def test_negative_stock_setting_allows_audited_sale(self):
		setting = ShopSetting.objects.get()
		setting.allow_negative_stock = True
		setting.save(update_fields=['allow_negative_stock'])
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 11}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '1100.00'}],
			actor=self.cashier,
		)
		self.assertEqual(get_stock_quantity(self.product), -1)
		movement = InventoryMovement.objects.get(reference=invoice.invoice_number)
		self.assertTrue(AuditLog.objects.filter(
			model_name='InventoryMovement', object_id=str(movement.pk)
		).exists())

	def test_cashier_cannot_apply_discount_but_supervisor_can(self):
		with self.assertRaises(ValidationError):
			create_sale(
				lines=[{'product_id': self.product.pk, 'quantity': 1}],
				tenders=[{'method': 'CARD_NETWORK', 'amount': '90.00'}],
				customer_id=self.customer.pk,
				discount_amount='10.00',
				actor=self.cashier,
			)
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '90.00'}],
			customer_id=self.customer.pk,
			discount_amount='10.00',
			actor=self.supervisor,
		)
		self.assertEqual(invoice.total_amount, Decimal('90.00'))


class SaleViewsTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='sale_view_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='sale_view_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.other_cashier = User.objects.create_user(
			username='sale_other_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.customer = Customer.objects.create(name='عميل شاشة البيع')
		category = Category.objects.create(name='تصنيف POS')
		self.product = Product.objects.create(
			category=category,
			name='منتج شاشة البيع',
			sku='POS-VIEW-01',
			barcode='200000007776',
			cost_price=Decimal('5.00'),
			sale_price=Decimal('12.00'),
		)
		ShopSetting.objects.create(name='البراق')
		record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.INITIAL,
			quantity_delta=4,
			unit_cost=Decimal('5.00'),
			actor=self.owner,
			notes='رصيد واجهة اختبار POS',
		)

	def test_pos_page_and_search_apis_require_authorized_login(self):
		self.client.force_login(self.cashier)
		self.assertEqual(self.client.get(reverse('pos')).status_code, 200)
		product_response = self.client.get(reverse('pos_product_search'), {'q': 'POS-VIEW'})
		customer_response = self.client.get(reverse('pos_customer_search'), {'q': 'عميل شاشة'})
		self.assertEqual(product_response.status_code, 200)
		self.assertEqual(product_response.json()['results'][0]['id'], self.product.pk)
		self.assertEqual(customer_response.json()['results'][0]['id'], self.customer.pk)

	def test_pos_submission_creates_invoice_and_preserves_cart_on_validation_error(self):
		self.client.force_login(self.cashier)
		response = self.client.post(reverse('pos'), {
			'items_json': json.dumps([{'product_id': self.product.pk, 'quantity': 1}]),
			'tenders_json': json.dumps([{'method': 'CARD_NETWORK', 'amount': '12.00'}]),
			'customer_id': '',
			'discount_amount': '0.00',
			'notes': '',
		})
		invoice = SaleInvoice.objects.get()
		self.assertRedirects(response, reverse('sale_detail', args=[invoice.pk]))
		invalid_response = self.client.post(reverse('pos'), {
			'items_json': json.dumps([{'product_id': self.product.pk, 'quantity': 100}]),
			'tenders_json': '[]',
			'customer_id': '',
			'discount_amount': '0.00',
			'notes': '',
		})
		self.assertEqual(invalid_response.status_code, 200)
		self.assertContains(invalid_response, 'منتج شاشة البيع')

	def test_cashier_cannot_view_another_cashiers_invoice(self):
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '12.00'}],
			actor=self.other_cashier,
		)
		self.client.force_login(self.cashier)
		response = self.client.get(reverse('sale_detail', args=[invoice.pk]))
		self.assertEqual(response.status_code, 403)

	def test_invoice_print_view_renders_shop_name_and_historical_line(self):
		invoice = create_sale(
			lines=[{'product_id': self.product.pk, 'quantity': 1}],
			tenders=[{'method': 'CARD_NETWORK', 'amount': '12.00'}],
			actor=self.owner,
		)
		self.client.force_login(self.owner)
		response = self.client.get(reverse('sale_print', args=[invoice.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'البراق')
		self.assertContains(response, '12.00')
