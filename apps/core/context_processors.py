from django.conf import settings

def shop_settings(request):
    """
    Context processor لتقديم الإعدادات العامة للمحل في جميع الواجهات تلقائيًا،
    وعلى رأسها اسم المحل الرسمي: البراق.
    """
    return {
        'SHOP_NAME': getattr(settings, 'SHOP_NAME', 'البراق'),
        'SHOP_TAGLINE': getattr(settings, 'SHOP_TAGLINE', 'إكسسوارات، زينة، وخدمات السيارات الفنية والملصقات'),
        'SHOP_PHONE': getattr(settings, 'SHOP_PHONE', '0500000000'),
    }
