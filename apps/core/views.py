from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def home_view(request):
    """
    الصفحة الرئيسية ولوحة التحكم الأساسية لنظام محل البراق
    """
    context = {
        'title': 'لوحة التحكم الرئيسية — محل البراق',
    }
    return render(request, 'home.html', context)
