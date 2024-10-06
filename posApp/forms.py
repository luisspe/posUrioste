from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.contrib.auth.models import User
from posApp.models import Sucursal, PlanInscripcion, Mensualidad, Salida

class SellerUserCreationForm(UserCreationForm):
    sucursal = forms.ModelChoiceField(queryset=Sucursal.objects.all(), required=True)
    
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2', 'sucursal')

    def __init__(self, *args, **kwargs):
        super(SellerUserCreationForm, self).__init__(*args, **kwargs)


class PlanInscripcionForm(forms.ModelForm):
    class Meta:
        model = PlanInscripcion
        fields = ['nombre', 'descripcion', 'precio', 'duracion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'required': True}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'required': True}),
            'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'required': True}),
            'duracion': forms.NumberInput(attrs={'class': 'form-control', 'required': True, 'min': '1'}),  # Campo duración
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nombre'].required = True
        self.fields['descripcion'].required = True
        self.fields['precio'].required = True
        self.fields['duracion'].required = True  # Aseguramos que la duración también sea requerida


class MensualidadForm(forms.ModelForm):
    tendered_amount_cash = forms.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False, 
        initial=0, 
        widget=forms.NumberInput(attrs={'style': 'display:none;'}),
        label=''
    )
    tendered_amount_card = forms.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        required=False, 
        initial=0, 
        widget=forms.NumberInput(attrs={'style': 'display:none;'}),
        label=''
    )

    class Meta:
        model = Mensualidad
        fields = ['fecha_vencimiento', 'plan_inscripcion', 'monto', 'tendered_amount_cash', 'tendered_amount_card']
        widgets = {
            'fecha_vencimiento': forms.DateInput(attrs={'type': 'date'}),
            'plan_inscripcion': forms.Select(attrs={'class': 'form-select'}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),  # Make monto field read-only
        }

class SalidaForm(forms.ModelForm):
    class Meta:
        model = Salida
        fields = ['concepto', 'monto', 'fecha', 'comentario']
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'comentario': forms.Textarea(attrs={'rows': 4}),
        }
        labels = {
            'concepto': 'Concepto',
            'monto': 'Monto',
            'fecha': 'Fecha',
            'comentario': 'Comentario (opcional)',
        }
        
class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ['nombre', 'direccion', 'telefono']