# C:\Java\PythonProjects\Inventarios\inventario\templatetags\custom_filters.py
from django import template

register = template.Library()

@register.filter
def format_number(value):
    """
    Formatea números enteros con puntos como separadores de miles
    Ejemplo: 5000 -> 5.000
    """
    try:
        if value is None or value == '':
            return '0'
        
        # Convertir a número
        num = float(value)
        
        # Si es número entero, mostrar sin decimales
        if num.is_integer():
            num = int(num)
            return f"{num:,}".replace(",", ".")
        else:
            # Si tiene decimales, mostrar con 2 decimales
            return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value

@register.filter
def format_currency(value):
    """
    Formatea números como moneda con símbolo $ y 2 decimales
    Ejemplo: 5000 -> $5.000,00
    """
    try:
        if value is None or value == '':
            return '$0,00'
        
        num = float(value)
        # Formatear con 2 decimales y separadores de miles
        formatted = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"${formatted}"
    except (ValueError, TypeError):
        return f"${value}"