document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const modal = document.getElementById('modalPerfiles');
    const nombreUsuarioSpan = document.getElementById('nombreUsuario');
    const btnContinuar = document.getElementById('btnContinuar');
    
    // Función para mostrar el modal
    function showModal() {
        if (modal) {
            modal.style.display = 'block';
        }
    }
    
    // Función para ocultar el modal
    function hideModal() {
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    // Función para mostrar mensajes de error
    function showErrorMessage(message) {
        // Crear elemento de alerta
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-error';
        alertDiv.textContent = message;
        
        // Insertar después del título h2
        const h2Element = document.querySelector('h2');
        if (h2Element) {
            h2Element.parentNode.insertBefore(alertDiv, h2Element.nextSibling);
        }
        
        // Desaparecer después de 5 segundos
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
    
    // Manejar el envío del formulario de login
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            // Mostrar indicador de carga
            const submitBtn = this.querySelector('button[type="submit"]');
            const originalText = submitBtn.textContent;
            submitBtn.textContent = "Autenticando...";
            submitBtn.disabled = true;
            
            // Limpiar mensajes anteriores
            const alertMessages = document.querySelectorAll('.alert');
            alertMessages.forEach(alert => alert.remove());
            
            // Llamar al endpoint de Django
            fetch('{% url "login" %}', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}&csrfmiddlewaretoken=${document.querySelector('[name=csrfmiddlewaretoken]').value}`
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.activo) {
                    // Mostrar modal de selección de perfil
                    if (nombreUsuarioSpan) {
                        nombreUsuarioSpan.textContent = data.usuario_nombre || username;
                    }
                    showModal();
                } else {
                    // Mostrar mensaje de error
                    const errorMessage = data.message || 'Error en la autenticación';
                    showErrorMessage(errorMessage);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showErrorMessage('Error de conexión');
            })
            .finally(() => {
                // Restaurar botón
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
            });
        });
    }
    
    // Manejar la selección de perfil
    if (btnContinuar) {
        btnContinuar.addEventListener('click', function() {
            const selectedProfile = document.querySelector('input[name="perfil_seleccionado"]:checked');
            
            if (!selectedProfile) {
                showErrorMessage('Por favor seleccione un perfil');
                return;
            }
            
            // Redireccionar al dashboard con el perfil seleccionado
            window.location.href = '{% url "dashboard" %}?perfil=' + encodeURIComponent(selectedProfile.value);
        });
    }
    
    // Cerrar modal si se hace click fuera del contenido
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                hideModal();
            }
        });
    }
    
    // Cerrar modal con tecla ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideModal();
        }
    });
});