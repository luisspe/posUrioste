from posApp.models import UserProfile

def user_profile(request):
    # Si el usuario está autenticado, intenta obtener su perfil
    if request.user.is_authenticated:
        try:
            profile = UserProfile.objects.get(user=request.user)
            return {'user_profile': profile}
        except UserProfile.DoesNotExist:
            return {'user_profile': None}
    # Si no está autenticado, devuelve un perfil nulo
    return {'user_profile': None}
