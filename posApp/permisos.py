def puede_borrar_salidas(user):
    """
    Solo quien tenga asignado a mano el permiso "Can delete salida" (en el admin, al usuario o a su grupo).
    No basta con ser superusuario: borrar una salida cambia los cortes de caja.
    """
    if not user.is_authenticated:
        return False
    return (user.user_permissions.filter(codename='delete_salida', content_type__app_label='posApp').exists() or
            user.groups.filter(permissions__codename='delete_salida', permissions__content_type__app_label='posApp').exists())
