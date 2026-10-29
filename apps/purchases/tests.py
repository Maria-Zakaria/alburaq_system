from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift
from core.models import ShopSetting
from inventory.models import InventoryMovement, MovementType
from inventory.services import get_stock_quantity, record_movement
from payments.models import FinancialTransaction, TransactionType
from products.models import Category, Product
from suppliers.models import Supplier

from .models import PurchaseInvoice, PurchaseInvoiceStatus, PurchaseReturn
from .services import create_purchase_invoice, create_purchase_return


class PurchaseServiceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='purchase_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='purchase_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.supplier = Supplier.objects.create(name='مورد الاختبار')
		category = Category.objects.create(name='تصنيف مشتريات الاختبار')
		self.product = Product.objects.create(
			category=category,
			name='منتج مشتريات الاختبار',
			sku='PUR-00001',
			barcode='200000008888',
			cost_price=Decimal('10.00'),
			sale_price=Decimal('20.00'),
		)
		ShopSetting.objects.create(name='البراق')

	def create_invoice(self, *, quantity=2, unit_cost='20.00', **kwargs):
		return create_purchase_invoice(
			supplier_id=self.supplier.pk,
			invoice_date=date(2026, 10, 7),
			lines=[{
				'product_id': self.product.pk,
				'quantity': quantity,
				'unit_cost': unit_cost,
			}],
			actor=self.owner,
			**kwargs,
		)

	def test_purchase_is_atomic_and_updates_stock_and_supplier_debt(self):
		invoice = self.create_invoice(discount_amount='5.00', tax_amount='1.00')
		self.assertEqual(invoice.status, PurchaseInvoiceStatus.COMPLETED)
		self.assertEqual(invoice.subtotal_amount, Decimal('40.00'))
		self.assertEqual(invoice.total_amount, Decimal('36.00'))
		self.assertEqual(invoice.remaining_amount, Decimal('36.00'))
		self.assertEqual(get_stock_quantity(self.product), 2)
		self.assertEqual(invoice.items.count(), 1)
		self.assertEqual(
			InventoryMovement.objects.get(reference=invoice.invoice_number).movement_type,
			MovementType.PURCHASE,
		)
		self.assertEqual(self.supplier.outstanding_balance, Decimal('36.00'))
		audit = AuditLog.objects.get(model_name='PurchaseInvoice', object_id=str(invoice.pk))
		self.assertEqual(audit.action, AuditAction.CREATE)

	def test_purchase_payment_is_a_financial_transaction(self):
		invoice = self.create_invoice(
			paid_amount='15.00',
			payment_method='BANK_TRANSFER',
			payment_reference='TR-001',
		)
		payment = FinancialTransaction.objects.get(purchase_invoice=invoice)
		self.assertEqual(payment.transaction_type, TransactionType.PURCHASE_PAYMENT)
		self.assertEqual(payment.amount, Decimal('15.00'))
		self.assertEqual(payment.reference, 'TR-001')
		self.assertTrue(AuditLog.objects.filter(
			model_name='FinancialTransaction', object_id=str(payment.pk)
		).exists())
		invoice.refresh_from_db()
		self.assertEqual(invoice.paid_amount, Decimal('15.00'))
		self.assertEqual(invoice.remaining_amount, Decimal('25.00'))
		self.assertEqual(self.supplier.outstanding_balance, Decimal('25.00'))

	def test_cash_payment_requires_one_open_shift_and_rolls_back_everything(self):
		with self.assertRaises(ValidationError):
			self.create_invoice(paid_amount='5.00', payment_method='CASH')
		self.assertFalse(PurchaseInvoice.objects.exists())
		self.assertFalse(InventoryMovement.objects.exists())
		self.assertFalse(FinancialTransaction.objects.exists())

		shift = CashShift.objects.create(cashier=self.owner, opening_balance=Decimal('100.00'))
		invoice = self.create_invoice(paid_amount='5.00', payment_method='CASH')
		payment = FinancialTransaction.objects.get(purchase_invoice=invoice)
		self.assertEqual(payment.shift, shift)

	def test_overpayment_rejects_without_partial_purchase(self):
		with self.assertRaises(ValidationError):
			self.create_invoice(paid_amount='41.00')
		self.assertFalse(PurchaseInvoice.objects.exists())
		self.assertFalse(InventoryMovement.objects.exists())

	def test_fractional_quantity_and_overprecision_amount_are_rejected(self):
		with self.assertRaises(ValidationError):
			self.create_invoice(quantity=Decimal('1.5'))
		with self.assertRaises(ValidationError):
			self.create_invoice(unit_cost='10.001')
		self.assertFalse(PurchaseInvoice.objects.exists())
		self.assertFalse(InventoryMovement.objects.exists())

	def test_duplicate_supplier_invoice_number_is_rejected_without_stock_change(self):
		self.create_invoice(supplier_invoice_number='EXT-555')
		with self.assertRaises(ValidationError):
			self.create_invoice(supplier_invoice_number='EXT-555')
		self.assertEqual(PurchaseInvoice.objects.count(), 1)
		self.assertEqual(get_stock_quantity(self.product), 2)

	def test_purchase_return_reverses_stock_and_supplier_liability(self):
		invoice = self.create_invoice()
		item = invoice.items.get()
		returned = create_purchase_return(
			purchase_invoice_id=invoice.pk,
			lines=[{'purchase_item_id': item.pk, 'quantity': 1}],
			actor=self.owner,
			reason='تالف عند الفحص',
		)
		self.assertEqual(returned.total_amount, Decimal('20.00'))
		self.assertEqual(get_stock_quantity(self.product), 1)
		self.assertEqual(self.supplier.outstanding_balance, Decimal('20.00'))
		self.assertEqual(
			InventoryMovement.objects.get(reference=returned.return_number).movement_type,
			MovementType.PURCHASE_RETURN,
		)
		audit = AuditLog.objects.get(model_name='PurchaseReturn', object_id=str(returned.pk))
		self.assertEqual(audit.action, AuditAction.RETURN)

	def test_cannot_return_more_than_received_even_across_multiple_returns(self):
		invoice = self.create_invoice(quantity=2)
		item = invoice.items.get()
		create_purchase_return(
			purchase_invoice_id=invoice.pk,
			lines=[{'purchase_item_id': item.pk, 'quantity': 1}],
			actor=self.owner,
			reason='الدفعة الأولى',
		)
		with self.assertRaises(ValidationError):
			create_purchase_return(
				purchase_invoice_id=invoice.pk,
				lines=[{'purchase_item_id': item.pk, 'quantity': 2}],
				actor=self.owner,
				reason='كمية زائدة',
			)
		self.assertEqual(PurchaseReturn.objects.count(), 1)
		self.assertEqual(get_stock_quantity(self.product), 1)

	def test_return_credit_uses_original_invoice_discount_and_tax_ratio(self):
		invoice = self.create_invoice(discount_amount='5.00', tax_amount='1.00')
		item = invoice.items.get()
		returned = create_purchase_return(
			purchase_invoice_id=invoice.pk,
			lines=[{'purchase_item_id': item.pk, 'quantity': 1}],
			actor=self.owner,
			reason='مرتجع من فاتورة عليها خصم وضريبة',
		)
		self.assertEqual(returned.total_amount, Decimal('18.00'))
		self.assertEqual(self.supplier.outstanding_balance, Decimal('18.00'))

	def test_return_after_payment_updates_due_but_preserves_paid_total(self):
		invoice = self.create_invoice(
			paid_amount='10.00',
			payment_method='BANK_TRANSFER',
		)
		item = invoice.items.get()
		create_purchase_return(
			purchase_invoice_id=invoice.pk,
			lines=[{'purchase_item_id': item.pk, 'quantity': 1}],
			actor=self.owner,
			reason='إرجاع بعد سداد جزئي',
		)
		invoice.refresh_from_db()
		self.assertEqual(invoice.paid_amount, Decimal('10.00'))
		self.assertEqual(invoice.remaining_amount, Decimal('10.00'))
		self.assertEqual(self.supplier.outstanding_balance, Decimal('10.00'))

	def test_return_fails_atomically_when_returned_goods_are_not_in_stock(self):
		invoice = self.create_invoice(quantity=1)
		item = invoice.items.get()
		record_movement(
			product_id=self.product.pk,
			movement_type=MovementType.SALE,
			quantity_delta=-1,
			actor=self.owner,
		)
		with self.assertRaises(ValidationError):
			create_purchase_return(
				purchase_invoice_id=invoice.pk,
				lines=[{'purchase_item_id': item.pk, 'quantity': 1}],
				actor=self.owner,
				reason='إرجاع لا يمكن إخراجه من المخزون',
			)
		self.assertFalse(PurchaseReturn.objects.exists())
		self.assertEqual(get_stock_quantity(self.product), 0)

	def test_cashier_cannot_use_purchase_service(self):
		with self.assertRaises(ValidationError):
			create_purchase_invoice(
				supplier_id=self.supplier.pk,
				invoice_date=date(2026, 10, 7),
				lines=[{'product_id': self.product.pk, 'quantity': 1, 'unit_cost': '1.00'}],
				actor=self.cashier,
			)
		self.assertFalse(PurchaseInvoice.objects.exists())


class SupplierAndPurchaseViewTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='supplier_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='supplier_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.supplier = Supplier.objects.create(name='مورد صفحات الاختبار')
		self.category = Category.objects.create(name='تصنيف صفحات الشراء')
		self.product = Product.objects.create(
			category=self.category,
			name='منتج صفحات الشراء',
			sku='PUR-VIEW-01',
			barcode='200000008887',
			cost_price=Decimal('5.00'),
			sale_price=Decimal('10.00'),
		)
		ShopSetting.objects.create(name='البراق')

	def test_cashier_cannot_access_supplier_or_purchase_pages(self):
		self.client.force_login(self.cashier)
		supplier_response = self.client.get(reverse('supplier_list'))
		purchase_response = self.client.get(reverse('purchase_list'))
		self.assertEqual(supplier_response.status_code, 403)
		self.assertEqual(purchase_response.status_code, 403)

	def test_owner_can_create_supplier_and_audit_it(self):
		self.client.force_login(self.owner)
		response = self.client.post(reverse('supplier_create'), {'name': 'مورد جديد'})
		self.assertEqual(response.status_code, 302)
		supplier = Supplier.objects.get(name='مورد جديد')
		self.assertTrue(AuditLog.objects.filter(
			model_name='Supplier', object_id=str(supplier.pk), action=AuditAction.CREATE
		).exists())

	def test_supplier_disable_is_post_only_and_preserves_record(self):
		self.client.force_login(self.owner)
		url = reverse('supplier_toggle_active', args=[self.supplier.pk])
		get_response = self.client.get(url)
		self.assertEqual(get_response.status_code, 405)
		response = self.client.post(url)
		self.assertEqual(response.status_code, 302)
		self.supplier.refresh_from_db()
		self.assertFalse(self.supplier.is_active)
		self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())

	def test_purchase_form_renders_dynamic_product_lines(self):
		self.client.force_login(self.owner)
		response = self.client.get(reverse('purchase_create'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id_items-__prefix__-product')

	def test_purchase_form_submission_creates_invoice_and_stock(self):
		self.client.force_login(self.owner)
		response = self.client.post(reverse('purchase_create'), {
			'supplier': self.supplier.pk,
			'supplier_invoice_number': 'VENDOR-101',
			'invoice_date': '2026-10-07',
			'discount_amount': '0.00',
			'tax_amount': '0.00',
			'paid_amount': '0.00',
			'payment_method': 'CASH',
			'payment_reference': '',
			'notes': '',
			'items-TOTAL_FORMS': '1',
			'items-INITIAL_FORMS': '0',
			'items-MIN_NUM_FORMS': '1',
			'items-MAX_NUM_FORMS': '1000',
			'items-0-product': self.product.pk,
			'items-0-quantity': '3',
			'items-0-unit_cost': '5.00',
		})
		self.assertEqual(response.status_code, 302)
		invoice = PurchaseInvoice.objects.get(supplier_invoice_number='VENDOR-101')
		self.assertEqual(get_stock_quantity(self.product), 3)
		self.assertEqual(invoice.total_amount, Decimal('15.00'))

	def test_purchase_return_form_renders_original_invoice_items(self):
		self.client.force_login(self.owner)
		invoice = create_purchase_invoice(
			supplier_id=self.supplier.pk,
			invoice_date=date(2026, 10, 7),
			lines=[{'product_id': self.product.pk, 'quantity': 2, 'unit_cost': '5.00'}],
			actor=self.owner,
		)
		response = self.client.get(reverse('purchase_return_create', args=[invoice.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'منتج صفحات الشراء')

	def test_purchase_return_submission_records_inventory_reversal(self):
		self.client.force_login(self.owner)
		invoice = create_purchase_invoice(
			supplier_id=self.supplier.pk,
			invoice_date=date(2026, 10, 7),
			lines=[{'product_id': self.product.pk, 'quantity': 2, 'unit_cost': '5.00'}],
			actor=self.owner,
		)
		item = invoice.items.get()
		response = self.client.post(reverse('purchase_return_create', args=[invoice.pk]), {
			'reason': 'تجربة مرتجع من الشاشة',
			'items-TOTAL_FORMS': '1',
			'items-INITIAL_FORMS': '0',
			'items-MIN_NUM_FORMS': '1',
			'items-MAX_NUM_FORMS': '1000',
			'items-0-purchase_item': item.pk,
			'items-0-quantity': '1',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(get_stock_quantity(self.product), 1)

# Create your tests here.
