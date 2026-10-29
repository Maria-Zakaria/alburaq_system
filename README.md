# نظام إدارة محل البراق — Al-Buraq Shop Management System

نظام إدارة متكامل واحترافي مصمم خصيصًا لمحل **البراق** لإكسسوارات وزينة السيارات، الخدمات الفنية والتركيبات، وطباعة وتركيب الاستيكرات.

## التقنيات المستخدمة
- **Backend:** Python 3.13 / Django 6.0 / Django REST Framework
- **Database:** PostgreSQL (مع دعم SQLite للتطوير المحلي)
- **Frontend:** Django Templates + Bootstrap 5 RTL + Custom CSS (Dark Navy & Cyan Identity)
- **Architecture:** Modular Architecture with Dedicated Business Logic Services Layer

## الهيكل العام للتطبيقات (`apps/`)
- `accounts`: إدارة المستخدمين، الأدوار، والصلاحيات (RBAC).
- `core`: الإعدادات العامة للمحل (الاسم الرسمي **البراق**، الترويسة، الشعار).
- `products`: المنتجات، التصنيفات، الباركود، SKU.
- `inventory`: حركات المخزون وحساب الكميات الحقيقية.
- `suppliers`: الموردون وفواتير المشتريات والديون.
- `purchases`: المشتريات وتكلفة البضاعة.
- `customers`: العملاء وتتبع الديون والمعاملات.
- `sales`: المبيعات، شاشة نقطة البيع (POS)، والأسعار التاريخية.
- `payments`: المعاملات المالية وطرق الدفع.
- `cashbox`: نظام الصندوق وإدارة ورديات الكاشير.
- `services_app`: الخدمات الفنية وطلبات الاستيكرات والطباعة.
- `employees`: الموظفون، الرواتب، والسحوبات.
- `expenses`: المصروفات التشغيلية والإيجار.
- `reports`: التقارير المالية والمخزنية والأرباح.
- `website`: الموقع العام المعروض للعملاء.
- `audit`: سجل التدقيق المالي والتشغيلي.

## التشغيل المحلي
```bash
python manage.py runserver
```
ثم افتح الرابط: `http://127.0.0.1:8000`
