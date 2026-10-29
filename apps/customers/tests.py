from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from cashbox.models import CashShift
from payments.models import FinancialTransaction, TransactionType
from sales.models import SaleInvoice, SaleStatus

from .forms import CustomerDebtPaymentForm
from .models import Customer
from .services import register_customer_debt_payment


class CustomerDebtServiceTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='customer_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='customer_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.customer = Customer.objects.create(name='عميل اختبار المرحلة السابعة')
		self.other_customer = Customer.objects.create(name='عميل آخر')
		self.invoice = self.create_invoice(self.customer, 'SALE-CUST-001', '100.00')

	def create_invoice(self, customer, invoice_number, amount):
		return SaleInvoice.objects.create(
			invoice_number=invoice_number,
			customer=customer,
			cashier=self.owner,
			subtotal=Decimal(amount),
			total_amount=Decimal(amount),
			paid_amount=Decimal('0.00'),
			remaining_amount=Decimal(amount),
			status=SaleStatus.COMPLETED,
		)

	def test_customer_balance_is_derived_from_invoices_and_collections(self):
		payment = FinancialTransaction.objects.create(
			transaction_type=TransactionType.CUSTOMER_DEBT_PAYMENT,
			amount=Decimal('30.00'),
			payment_method='BANK_TRANSFER',
			sale_invoice=self.invoice,
			customer=self.customer,
			user=self.owner,
			reference='TRANSFER-001',
		)
		self.assertEqual(self.customer.outstanding_balance, Decimal('70.00'))
		self.assertEqual(payment.customer, self.customer)

	def test_partial_payment_updates_invoice_due_and_customer_balance(self):
		payment = register_customer_debt_payment(
			customer_id=self.customer.pk,
			sale_invoice_id=self.invoice.pk,
			amount='35.00',
			payment_method='BANK_TRANSFER',
			reference='BANK-001',
			actor=self.owner,
		)
		self.invoice.refresh_from_db()
		self.assertEqual(payment.transaction_type, TransactionType.CUSTOMER_DEBT_PAYMENT)
		self.assertEqual(payment.amount, Decimal('35.00'))
		self.assertEqual(self.invoice.paid_amount, Decimal('35.00'))
		self.assertEqual(self.invoice.remaining_amount, Decimal('65.00'))
		self.assertEqual(self.customer.outstanding_balance, Decimal('65.00'))
		audit = AuditLog.objects.get(model_name='FinancialTransaction', object_id=str(payment.pk))
		self.assertEqual(audit.action, AuditAction.DEBT_ADJUST)

	def test_full_payment_closes_due_without_overpayment(self):
		register_customer_debt_payment(
			customer_id=self.customer.pk,
			sale_invoice_id=self.invoice.pk,
			amount='100.00',
			payment_method='CARD_NETWORK',
			actor=self.owner,
		)
		self.invoice.refresh_from_db()
		self.assertEqual(self.invoice.remaining_amount, Decimal('0.00'))
		self.assertEqual(self.customer.outstanding_balance, Decimal('0.00'))

	def test_overpayment_is_rejected_without_creating_transaction(self):
		with self.assertRaises(ValidationError):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=self.invoice.pk,
				amount='100.01',
				payment_method='BANK_TRANSFER',
				actor=self.owner,
			)
		self.assertFalse(FinancialTransaction.objects.exists())
		self.invoice.refresh_from_db()
		self.assertEqual(self.invoice.remaining_amount, Decimal('100.00'))

	def test_payment_cannot_be_attached_to_another_customers_invoice(self):
		other_invoice = self.create_invoice(self.other_customer, 'SALE-CUST-002', '50.00')
		with self.assertRaises(SaleInvoice.DoesNotExist):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=other_invoice.pk,
				amount='10.00',
				payment_method='BANK_TRANSFER',
				actor=self.owner,
			)
		self.assertFalse(FinancialTransaction.objects.exists())

	def test_cash_payment_requires_exactly_one_open_shift(self):
		with self.assertRaises(ValidationError):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=self.invoice.pk,
				amount='10.00',
				payment_method='CASH',
				actor=self.owner,
			)
		shift = CashShift.objects.create(cashier=self.owner, opening_balance=Decimal('50.00'))
		payment = register_customer_debt_payment(
			customer_id=self.customer.pk,
			sale_invoice_id=self.invoice.pk,
			amount='10.00',
			payment_method='CASH',
			actor=self.owner,
		)
		self.assertEqual(payment.shift, shift)

	def test_cashier_cannot_record_customer_debt_payment(self):
		with self.assertRaises(ValidationError):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=self.invoice.pk,
				amount='10.00',
				payment_method='BANK_TRANSFER',
				actor=self.cashier,
			)
		self.assertFalse(FinancialTransaction.objects.exists())

	def test_fractional_money_precision_is_rejected(self):
		with self.assertRaises(ValidationError):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=self.invoice.pk,
				amount='10.001',
				payment_method='BANK_TRANSFER',
				actor=self.owner,
			)

	def test_amount_above_financial_field_capacity_is_rejected(self):
		with self.assertRaises(ValidationError):
			register_customer_debt_payment(
				customer_id=self.customer.pk,
				sale_invoice_id=self.invoice.pk,
				amount='10000000000.00',
				payment_method='BANK_TRANSFER',
				actor=self.owner,
			)
		self.assertFalse(FinancialTransaction.objects.exists())


class CustomerViewsTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(
			username='customer_view_owner', password='test-password', role=UserRole.OWNER
		)
		self.cashier = User.objects.create_user(
			username='customer_view_cashier', password='test-password', role=UserRole.CASHIER
		)
		self.customer = Customer.objects.create(name='عميل الواجهة')
		self.invoice = SaleInvoice.objects.create(
			invoice_number='SALE-VIEW-001',
			customer=self.customer,
			cashier=self.owner,
			subtotal=Decimal('80.00'),
			total_amount=Decimal('80.00'),
			paid_amount=Decimal('0.00'),
			remaining_amount=Decimal('80.00'),
			status=SaleStatus.COMPLETED,
		)

	def test_cashier_cannot_open_customer_debt_pages(self):
		self.client.force_login(self.cashier)
		response = self.client.get(reverse('customer_list'))
		self.assertEqual(response.status_code, 403)

	def test_owner_can_list_and_view_customer_debt(self):
		self.client.force_login(self.owner)
		list_response = self.client.get(reverse('customer_list'))
		detail_response = self.client.get(reverse('customer_detail', args=[self.customer.pk]))
		self.assertEqual(list_response.status_code, 200)
		self.assertContains(list_response, '80.00')
		self.assertEqual(
			list_response.context['page_obj'][0].calculated_balance,
			Decimal('80.00'),
		)
		self.assertEqual(detail_response.status_code, 200)
		self.assertContains(detail_response, 'SALE-VIEW-001')

	def test_owner_can_create_customer_without_vehicle_profile(self):
		self.client.force_login(self.owner)
		response = self.client.post(reverse('customer_create'), {
			'name': 'عميل بلا ملف مركبة',
			'phone': '',
			'email': '',
			'address': '',
			'notes': '',
		})
		self.assertEqual(response.status_code, 302)
		customer = Customer.objects.get(name='عميل بلا ملف مركبة')
		self.assertTrue(AuditLog.objects.filter(
			model_name='Customer', object_id=str(customer.pk), action=AuditAction.CREATE
		).exists())

	def test_debt_payment_form_excludes_other_customers_invoices(self):
		self.client.force_login(self.owner)
		response = self.client.get(reverse('customer_debt_payment', args=[self.customer.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.invoice.invoice_number)
