from . import views
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic.base import RedirectView

urlpatterns = [
    path('redirect-admin', RedirectView.as_view(url="/admin"),name="redirect-admin"),
    path('', views.home, name="home-page"),
    path('login', views.CustomLoginView.as_view(), name="login"),
    path('userlogin', views.login_user, name="login-user"),
    path('logout', views.logoutuser, name="logout"),
    path('category', views.category, name="category-page"),
    path('cambiar_sucursal/', views.cambiar_sucursal, name='cambiar-sucursal'),
    path('manage_category', views.manage_category, name="manage_category-page"),
    path('save_category', views.save_category, name="save-category-page"),
    path('delete_category', views.delete_category, name="delete-category"),
    path('products', views.products, name="product-page"),
    path('clientes', views.clients, name="client-page"),
    path('manage_products', views.manage_products, name="manage_products-page"),
    path('manage_clients', views.manage_clients, name="manage_clients-page"),
    path('save_product', views.save_product, name="save-product-page"),
    path('save_client', views.save_client, name="save-client-page"),
    path('delete_product', views.delete_product, name="delete-product"),
    path('pos', views.pos, name="pos-page"),
    path('checkout-modal', views.checkout_modal, name="checkout-modal"),
    path('save-pos', views.save_pos, name="save-pos"),
    path('sales', views.salesList, name="sales-page"),
    path('receipt', views.receipt, name="receipt-modal"),
    path('delete_sale', views.delete_sale, name="delete-sale"),
    path('create-seller/', views.SellerUserCreateView.as_view(), name='create_seller_user'),
    path('delete_cliente/', views.delete_cliente, name='delete_cliente'),
    path('plans/', views.plans, name='plans-page'),
    path('editar-plan/<int:pk>/', views.editar_plan, name='editar-plan'),
    path('delete_plan/', views.delete_plan, name='delete-plan'),
    path('clientes/<int:cliente_id>/mensualidades/', views.cliente_mensualidades, name='cliente_mensualidades'),
    path('salida/add/', views.add_salida, name='add_salida'),
    path('clientes/<int:cliente_id>/mensualidades/pagar/', views.pagar_primera_mensualidad, name='pagar_primera_mensualidad'),
    path('seleccionar-mensualidades/<int:cliente_id>/', views.seleccionar_mensualidades, name='seleccionar-mensualidades'),
    path('generar-mensualidades/<int:cliente_id>/', views.generar_mensualidades, name='generar-mensualidades'),
    path('plan-inscripcion/create/', views.create_plan_inscripcion, name='create_plan_inscripcion'),
    path('create-sucursal/', views.create_sucursal, name='create_sucursal'),
    path('export_sales_to_excel/', views.export_sales_to_excel, name='export_sales_to_excel'),
]