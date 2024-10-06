from django.utils.deprecation import MiddlewareMixin
from .models import Sucursal, UserProfile

class SucursalMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            try:
                user_profile = UserProfile.objects.get(user=request.user)
                
                if user_profile.is_manager:
                    sucursal_id = request.session.get('sucursal_id')
                    if sucursal_id:
                        try:
                            request.sucursal = Sucursal.objects.get(id=sucursal_id)
                        except Sucursal.DoesNotExist:
                            request.sucursal = None
                    else:
                        request.sucursal = None
                else:
                    request.sucursal = user_profile.sucursal
            except UserProfile.DoesNotExist:
                request.sucursal = None
        else:
            request.sucursal = None