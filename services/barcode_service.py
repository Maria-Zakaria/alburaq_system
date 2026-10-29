import random
import string
from products.models import Product

class BarcodeService:
    """
    خدمة برمجية لتوليد والتحقق من الباركود والـ SKU لمنتجات محل البراق
    """
    @staticmethod
    def generate_unique_barcode():
        """
        توليد رقم باركود فريد مخصص للنظام (رمز مكون من 12 إلى 13 رقمًا)
        """
        while True:
            # البادئة 200 للمنتجات الداخلية بمحل البراق
            code = "200" + "".join([str(random.randint(0, 9)) for _ in range(9)])
            if not Product.objects.filter(barcode=code).exists():
                return code

    @staticmethod
    def generate_unique_sku(prefix="ALB"):
        """
        توليد كود SKU فريد للمنتج (مثل ALB-8392)
        """
        while True:
            num = "".join([str(random.randint(0, 9)) for _ in range(5)])
            sku = f"{prefix}-{num}"
            if not Product.objects.filter(sku=sku).exists():
                return sku
