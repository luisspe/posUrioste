from pickle import FALSE
from django.shortcuts import redirect, render
from django.http import HttpResponse
from flask import jsonify
from posApp.models import Category, Products, Sales, salesItems, Clientes, Genero, Levels, FormaPago
from django.db.models import Count, Sum, Q
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect
import json, sys
from datetime import date, datetime
from django.contrib.auth.models import User
from django.utils import timezone
# Login
def login_user(request):
    logout(request)
    resp = {"status":'failed','msg':''}
    username = ''
    password = ''
    if request.POST:
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                resp['status']='success'
            else:
                resp['msg'] = "Incorrect username or password"
        else:
            resp['msg'] = "Incorrect username or password"
    return HttpResponse(json.dumps(resp),content_type='application/json')

#Logout
def logoutuser(request):
    logout(request)
    return redirect('/')

# Create your views here.
@login_required
def home(request):
    now = datetime.now()
    current_year = now.strftime("%Y")
    current_month = now.strftime("%m")
    current_day = now.strftime("%d")
    categories = len(Category.objects.all())
    products = len(Products.objects.all())
    transaction = len(Sales.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day
    ))
    today_sales = Sales.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        date_added__day = current_day
    ).all()
    month_sales = Sales.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        
    ).all()

    month_sales_cash = Sales.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        tipoPago=1
        
    ).all()
    month_sales_bank = Sales.objects.filter(
        date_added__year=current_year,
        date_added__month = current_month,
        tipoPago=2
        
    ).all()
    total_sales = sum(today_sales.values_list('grand_total',flat=True))
    month_sales = sum(month_sales.values_list('grand_total',flat=True))
    month_sales_cash = sum(month_sales_cash.values_list('grand_total',flat=True))
    month_sales_bank = sum(month_sales_bank.values_list('grand_total',flat=True))
    context = {
        'page_title':'Home',
        'categories' : categories,
        'products' : products,
        'transaction' : transaction,
        'total_sales' : total_sales,
        'month_sales': month_sales,
        'month_sales_cash': month_sales_cash,
        'month_sales_bank': month_sales_bank,
    }
    return render(request, 'posApp/home.html',context)


def about(request):
    context = {
        'page_title':'About',
    }
    return render(request, 'posApp/about.html',context)

#Categories
@login_required
def category(request):
    category_list = Category.objects.all()
    # category_list = {}
    context = {
        'page_title':'Categorias',
        'category':category_list,
    }
    return render(request, 'posApp/category.html',context)
@login_required
def manage_category(request):
    category = {}
    if request.method == 'GET':
        data =  request.GET
        id = ''
        if 'id' in data:
            id= data['id']
        if id.isnumeric() and int(id) > 0:
            category = Category.objects.filter(id=id).first()
    
    context = {
        'category' : category
    }
    return render(request, 'posApp/manage_category.html',context)

@login_required
def save_category(request):
    data =  request.POST
    resp = {'status':'failed'}
    try:
        if (data['id']).isnumeric() and int(data['id']) > 0 :
            save_category = Category.objects.filter(id = data['id']).update(name=data['name'], description = data['description'],status = data['status'])
        else:
            save_category = Category(name=data['name'], description = data['description'],status = data['status'])
            save_category.save()
        resp['status'] = 'success'
        messages.success(request, 'Categoria guardada con exito.')
    except:
        resp['status'] = 'failed'
    return HttpResponse(json.dumps(resp), content_type="application/json")

@login_required
def delete_category(request):
    data =  request.POST
    resp = {'status':''}
    try:
        Category.objects.filter(id = data['id']).delete()
        resp['status'] = 'success'
        messages.success(request, 'Categoria eliminada con exito.')
    except:
        resp['status'] = 'failed'
    return HttpResponse(json.dumps(resp), content_type="application/json")

# Products
@login_required
def products(request):
    product_list = Products.objects.all()
    context = {
        'page_title':'Productos',
        'products':product_list,
    }
    return render(request, 'posApp/products.html',context)


@login_required
def clients(request):
    clients_list = Clientes.objects.all()
    
    query = request.GET.get('q')

    if query:
        # Perform the search and return the results
        results = Clientes.objects.filter(Q(nombre__contains=query) | Q(apellido_paterno__contains=query) | Q(apellido_materno__contains=query))
        productos_inventario = None
    else:
        results = None

    context = {
        'page_title':'Clientes',
        'clients':clients_list,
        'query': query,
        'results': results
    }
    return render(request, 'posApp/clients.html',context)


@login_required
def manage_clients(request):
    client = {}
    genero = Genero.objects.all()
    nivel = Levels.objects.all()
    if request.method == 'GET':
        data =  request.GET
        id = ''
        if 'id' in data:
            id= data['id']
        if id.isnumeric() and int(id) > 0:
            client = Clientes.objects.filter(id=id).first()
    
    context = {
        'client' : client,
        'generos' : genero,
        'niveles' : nivel
    }
    return render(request, 'posApp/manage_client.html',context)

@login_required
def save_client(request):
    data =  request.POST
    resp = {'status':'failed'}
    id= ''
    if 'id' in data:
        id = data['id']
    if id.isnumeric() and int(id) > 0:
        check = Clientes.objects.exclude(id=id).filter(nombre=data['nombre']).all()
    else:
        check = Clientes.objects.filter(nombre=data['nombre'], apellido_paterno=data['apellido_paterno'], apellido_materno=data['apellido_materno']).all()
    if len(check) > 0 :
        resp['msg'] = "cliente ya existe"
    
    else:
        genero = Genero.objects.filter(id = data['genero_id']).first()
        nivel = Levels.objects.filter(id = data['nivel']).first()
        try:
            if (data['id']).isnumeric() and int(data['id']) > 0 :
                save_client = Clientes.objects.filter(id = data['id']).update(nombre=data['nombre'], 
                genero_id=genero, 
                nivel=nivel, apellido_paterno=data['apellido_paterno'], apellido_materno=data['apellido_materno'], celular=data['celular'], fecha_nacimiento=data['fecha_nacimiento'],
                codigo_postal=data['codigo_postal'], 
                email=data['email'], 
                contacto_emergencia=data['contacto_emergencia'], emergency_phone=data['emergency_phone'], 
                sangre=data['sangre'], 
                pay_day=data['pay_day'], 
                horario=data['horario'], 
                suburbio=data['suburbio'], 
                direccion=data['direccion'], 
                condicion_medica=data['condicion_medica'],
                status = data['status'])

            else:
                save_client = Clientes(nombre=data['nombre'], 
                genero=genero, 
                nivel=nivel, apellido_paterno=data['apellido_paterno'], apellido_materno=data['apellido_materno'], celular=data['celular'], fecha_nacimiento=data['fecha_nacimiento'],
                codigo_postal=data['codigo_postal'], 
                email=data['email'], 
                contacto_emergencia=data['contacto_emergencia'], emergency_phone=data['emergency_phone'], 
                sangre=data['sangre'], 
                pay_day=data['pay_day'], 
                horario=data['horario'], 
                suburbio=data['suburbio'], 
                direccion=data['direccion'], 
                condicion_medica=data['condicion_medica'],
                status = data['status'])
                save_client.save()

            resp['status'] = 'success'
            messages.success(request, 'cliente guardado con exito.')
                
        except:
            resp['status'] = 'failed'
    return HttpResponse(json.dumps(resp), content_type="application/json")


@login_required
def manage_products(request):
    product = {}
    categories = Category.objects.filter(status = 1).all()
    if request.method == 'GET':
        data =  request.GET
        id = ''
        if 'id' in data:
            id= data['id']
        if id.isnumeric() and int(id) > 0:
            product = Products.objects.filter(id=id).first()
    
    context = {
        'product' : product,
        'categories' : categories
    }
    return render(request, 'posApp/manage_product.html',context)
def test(request):
    categories = Category.objects.all()
    context = {
        'categories' : categories
    }
    return render(request, 'posApp/test.html',context)
@login_required
def save_product(request):
    data =  request.POST
    resp = {'status':'failed'}
    id= ''
    if 'id' in data:
        id = data['id']
    if id.isnumeric() and int(id) > 0:
        check = Products.objects.exclude(id=id).filter(code=data['code']).all()
    else:
        check = Products.objects.filter(code=data['code']).all()
    if len(check) > 0 :
        resp['msg'] = "Product Code Already Exists in the database"
    else:
        category = Category.objects.filter(id = data['category_id']).first()
        try:
            if (data['id']).isnumeric() and int(data['id']) > 0 :
                save_product = Products.objects.filter(id = data['id']).update(code=data['code'], category_id=category, name=data['name'], description = data['description'], price = float(data['price']),status = data['status'])
            else:
                save_product = Products(code=data['code'], category_id=category, name=data['name'], description = data['description'], price = float(data['price']),status = data['status'])
                save_product.save()
            resp['status'] = 'success'
            messages.success(request, 'Producto guardado con exito.')
        except:
            resp['status'] = 'failed'
    return HttpResponse(json.dumps(resp), content_type="application/json")

@login_required
def delete_product(request):
    data =  request.POST
    resp = {'status':''}
    try:
        Products.objects.filter(id = data['id']).delete()
        resp['status'] = 'success'
        messages.success(request, 'Producto eliminado con exito.')
    except:
        resp['status'] = 'failed'
    return HttpResponse(json.dumps(resp), content_type="application/json")
@login_required
def pos(request):
    products = Products.objects.filter(status = 1)
    clients = Clientes.objects.filter(status = 1)
    tipoPago = FormaPago.objects.all()
    product_json = [] 
    client_json = []
    for product in products:
        product_json.append({'id':product.id, 'name':product.name, 'price':float(product.price)})

    for client in clients:
        client_json.append({'id':client.id})
    context = {
        'page_title' : "Punto de Ventas",
        'products' : products,
        'clients' : clients,
        'product_json' : json.dumps(product_json),
        'client_json': json.dumps(client_json),
        'tipo_pago' : tipoPago
    }
    # return HttpResponse('')
    return render(request, 'posApp/pos.html',context)

@login_required
def checkout_modal(request):
   
    grand_total = 0
    if 'grand_total' in request.GET:
        grand_total = request.GET['grand_total']
    context = {
        'grand_total' : grand_total,
       
    }
    return render(request, 'posApp/checkout.html',context)

@login_required
def save_pos(request):
    resp = {'status':'failed','msg':''}
    data = request.POST
    usuario_actual = request.user
    print(data)
    pref = datetime.now().year + datetime.now().year
    client = Clientes.objects.filter(id=data['client']).first()
    tipoPago = FormaPago.objects.filter(id=data['tipoPago']).first()
    
    i = 1
    while True:
        code = '{:0>5}'.format(i)
        i += int(1)
        check = Sales.objects.filter(code = str(pref) + str(code)).all()
        if len(check) <= 0:
            break
    code = str(pref) + str(code)

    try:
        sales = Sales(code=code, sub_total = data['sub_total'], tax = data['tax'], tax_amount = data['tax_amount'], grand_total = data['grand_total'], tendered_amount = data['tendered_amount'], tendered_amount_card = data['tendered_amount_card'], client=client, amount_change = data['amount_change'] , tipoPago = tipoPago,usuario=usuario_actual, comentario=data['comentario'] ).save()
        sale_id = Sales.objects.last().pk
        i = 0
        for prod in data.getlist('product_id[]'):
            product_id = prod 
            sale = Sales.objects.filter(id=sale_id).first()
            product = Products.objects.filter(id=product_id).first()
            client = Clientes.objects.filter(id=data['client']).first()
            qty = data.getlist('qty[]')[i] 
            price = data.getlist('price[]')[i] 
            total = float(qty) * float(price)
            print({'sale_id' : sale, 'product_id' : product, 'client':client , 'qty' : qty, 'price' : price, 'total' : total})
            salesItems(sale_id = sale, client = client, product_id = product, qty = qty, price = price, total = total).save()
            i += int(1)
        resp['status'] = 'success'
        resp['sale_id'] = sale_id
        messages.success(request, "La venta ha sido guardada.")
    except:
        resp['msg'] = "An error occured"
        print("Unexpected error:", sys.exc_info()[0])
    return HttpResponse(json.dumps(resp),content_type="application/json")

@login_required
def salesList(request):
    
    today = timezone.now()
    clientes = Clientes.objects.all()
    formapago = FormaPago.objects.all()
    totalEfectivo = Sales.objects.filter(date_added__date=today, tipoPago=1).aggregate(Sum('grand_total'))['grand_total__sum']
    totalBanco = Sales.objects.filter(date_added__date=today, tipoPago=2).aggregate(Sum('grand_total'))['grand_total__sum']
    
    if request.method == 'GET':
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        cliente = request.GET.get('cliente_id')
        forma_pago = request.GET.get('formapago_id')
        query = request.GET.get('q')

        if start_date and end_date and forma_pago and cliente:
            sales = Sales.objects.filter(date_added__range=(start_date, end_date), tipoPago=forma_pago, client=cliente).order_by('-date_added')
            total_money = Sales.objects.filter(date_added__range=(start_date, end_date), tipoPago=forma_pago).aggregate(Sum('grand_total'))['grand_total__sum']

        elif start_date and end_date and forma_pago:
            sales = Sales.objects.filter(date_added__range=(start_date, end_date), tipoPago=forma_pago).order_by('-date_added')
            total_money = Sales.objects.filter(date_added__range=(start_date, end_date), tipoPago=forma_pago).aggregate(Sum('grand_total'))['grand_total__sum']

        elif start_date and end_date and cliente:
            sales = Sales.objects.filter(date_added__range=(start_date, end_date), client=cliente).order_by('-date_added')
            total_money = Sales.objects.filter(date_added__range=(start_date, end_date)).aggregate(Sum('grand_total'))['grand_total__sum']

        elif start_date and end_date:
            sales = Sales.objects.filter(date_added__range=(start_date, end_date)).order_by('-date_added')
            total_money = Sales.objects.filter(date_added__range=(start_date, end_date)).aggregate(Sum('grand_total'))['grand_total__sum']

        elif forma_pago:
            sales = Sales.objects.filter(tipoPago=forma_pago).order_by('-date_added')
            total_money = Sales.objects.filter(tipoPago=forma_pago).aggregate(Sum('grand_total'))['grand_total__sum']

        elif cliente:
            sales = Sales.objects.filter(client=cliente).order_by('-date_added')
            total_money = Sales.objects.filter(client=cliente).aggregate(Sum('grand_total'))['grand_total__sum']

        elif cliente and forma_pago:
            sales = Sales.objects.filter(client=cliente, tipoPago=forma_pago).order_by('-date_added')
            total_money = Sales.objects.filter(client=cliente, tipoPago=forma_pago).aggregate(Sum('grand_total'))['grand_total__sum']
        
        else:
            sales = Sales.objects.filter(date_added__date=today).order_by('-date_added')
            total_money = Sales.objects.filter(date_added__date=today).aggregate(Sum('grand_total'))['grand_total__sum']
    
    sale_data = []
    for sale in sales:
        data = {}
        for field in sale._meta.get_fields(include_parents=False):
            if field.related_model is None:
                data[field.name] = getattr(sale,field.name)
        data['items'] = salesItems.objects.filter(sale_id=sale).all()
        data['client'] = sale.client
        data['tipoPago'] = sale.tipoPago
        data['usuario'] = sale.usuario
        data['item_count'] = len(data['items'])
        if 'tax_amount' in data:
            data['tax_amount'] = format(float(data['tax_amount']), '.2f')
        sale_data.append(data)

    context = {
        'page_title': 'Sales Transactions',
        'sale_data': sale_data,
        'total': total_money,
        'formapago': formapago,
        'clientes': clientes,
        'totalEfectivo': totalEfectivo,
        'totalBanco': totalBanco
    }
    return render(request, 'posApp/sales.html', context)

@login_required
def receipt(request):
    id = request.GET.get('id')
    sales = Sales.objects.filter(id = id).first()
    transaction = {}
    for field in Sales._meta.get_fields():
        if field.related_model is None:
            transaction[field.name] = getattr(sales,field.name)
    if 'tax_amount' in transaction:
        transaction['tax_amount'] = format(float(transaction['tax_amount']))
    ItemList = salesItems.objects.filter(sale_id = sales).all()
    print(sales)
    print(transaction)
    context = {
        "transaction" : transaction,
        "salesItems" : ItemList,
        "sales": sales
    }

    return render(request, 'posApp/receipt.html',context)
    # return HttpResponse('')
@user_passes_test(lambda u: u.is_superuser)
@login_required
def delete_sale(request):
    resp = {'status':'failed', 'msg':''}
    id = request.POST.get('id')
    try:
        delete = Sales.objects.filter(id = id).delete()
        resp['status'] = 'success'
        messages.success(request, 'La venta ha sido eliminada.')
    except:
        resp['msg'] = "An error occured"
        print("Unexpected error:", sys.exc_info()[0])
    return HttpResponse(json.dumps(resp), content_type='application/json')