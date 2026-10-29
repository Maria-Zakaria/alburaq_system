from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import AccessMixin
from accounts.models import UserRole

def role_required(*allowed_roles):
    """
    Decorator لحماية الـ Views بناءً على دور المستخدم المستهدف.
    يتم الفحص على مستوى الخادم SERVER-SIDE ENFORCEMENT.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            
            # المدير له صلاحية الوصول لكافة الشاشات دائمًا
            if request.user.is_superuser or request.user.role == UserRole.OWNER or request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            raise PermissionDenied("عذرًا! ليس لديك الصلاحية الكافية للوصول إلى هذه الشاشة أو تنفيذ هذه العملية.")
        return _wrapped_view
    return decorator

class RoleRequiredMixin(AccessMixin):
    """
    Class-based View Mixin لمنع المستخدمين غير المصرح لهم على مستوى الخادم.
    """
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        if request.user.is_superuser or request.user.role == UserRole.OWNER or request.user.role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)
        
        raise PermissionDenied("عذرًا! ليس لديك الصلاحية الكافية للوصول إلى هذه الشاشة أو تنفيذ هذه العملية.")

class OwnerRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.OWNER]

class SupervisorRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR]

class CashierRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.CASHIER]

class InventoryClerkRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.INVENTORY_CLERK]

class TechnicianRequiredMixin(RoleRequiredMixin):
    allowed_roles = [UserRole.OWNER, UserRole.SHIFT_SUPERVISOR, UserRole.TECHNICIAN]
