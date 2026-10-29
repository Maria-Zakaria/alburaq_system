from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.models import User, UserRole
from accounts.forms import UserLoginForm, UserForm, ChangePasswordForm
from accounts.permissions import role_required

def login_view(request):
    """
    شاشة تسجيل الدخول لمستخدمي محل البراق
    """
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"أهلاً بك يا {user.get_full_name() or user.username}! تم تسجيل الدخول بنجاح.")
            
            # التوجيه الذكي حسب دور المستخدم
            if user.role == UserRole.CASHIER:
                return redirect('home') # سيُوجه مستقبلاً لمستند POS
            return redirect('home')
        else:
            messages.error(request, "اسم المستخدم أو كلمة المرور غير صحيحة. يُرجى المحاولة مجددًا.")
    else:
        form = UserLoginForm()
    
    return render(request, 'accounts/login.html', {'form': form, 'title': 'تسجيل الدخول — محل البراق'})

@login_required
def logout_view(request):
    """
    تسجيل الخروج الآمن
    """
    logout(request)
    messages.info(request, "تم تسجيل الخروج بنجاح من نظام البراق.")
    return redirect('login')

@login_required
@role_required(UserRole.OWNER)
def user_list_view(request):
    """
    قائمة إدارة المستخدمين (خاصة بالمالك / المدير فقط)
    """
    users = User.objects.all().order_by('-id')
    return render(request, 'accounts/user_list.html', {
        'users': users,
        'title': 'إدارة المستخدمين والصلاحيات — البراق'
    })

@login_required
@role_required(UserRole.OWNER)
def user_create_view(request):
    """
    إضافة مستخدم جديد وتحديد دوره
    """
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"تم إضافة المستخدم {user.username} بنجاح.")
            return redirect('user_list')
        else:
            messages.error(request, "حدث خطأ أثناء إضافة المستخدم. تحقق من البيانات المدخلة.")
    else:
        form = UserForm()
    
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'action': 'create',
        'title': 'إضافة مستخدم جديد — البراق'
    })

@login_required
@role_required(UserRole.OWNER)
def user_update_view(request, pk):
    """
    تعديل بيانات وصلاحية مستخدم
    """
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user_obj)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"تم تحديث بيانات المستخدم {user.username} بنجاح.")
            return redirect('user_list')
        else:
            messages.error(request, "حدث خطأ أثناء تحديث المستخدم.")
    else:
        form = UserForm(instance=user_obj)
    
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'action': 'update',
        'user_obj': user_obj,
        'title': f'تعديل المستخدم {user_obj.username} — البراق'
    })

@login_required
@role_required(UserRole.OWNER)
def user_toggle_status_view(request, pk):
    """
    تفعيل أو تعطيل حساب مستخدم دون حذفه فعليًا (Soft Disable)
    """
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.pk == request.user.pk:
        messages.error(request, "لا يمكنك تعطيل حسابك الشخصي أثناء تسجيل الدخول منه!")
        return redirect('user_list')
    
    user_obj.is_active = not user_obj.is_active
    user_obj.save()
    status_text = "تفعيل" if user_obj.is_active else "تعطيل"
    messages.success(request, f"تم {status_text} حساب المستخدم {user_obj.username} بنجاح.")
    return redirect('user_list')

@login_required
def change_password_view(request):
    """
    تغيير كلمة المرور للمستخدم الحالي
    """
    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            user = request.user
            if not user.check_password(form.cleaned_data['old_password']):
                messages.error(request, "كلمة المرور الحالية غير صحيحة.")
            else:
                user.set_password(form.cleaned_data['new_password'])
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "تم تغيير كلمة المرور بنجاح.")
                return redirect('home')
    else:
        form = ChangePasswordForm()
    
    return render(request, 'accounts/change_password.html', {
        'form': form,
        'title': 'تغيير كلمة المرور — البراق'
    })
