// Dashboard Menu Handler - Versión final y funcional
console.log('🚀 Cargando Dashboard JS...');

document.addEventListener('DOMContentLoaded', function() {
    console.log('🎯 Dashboard JS iniciando...');
    
    // Obtener elementos del DOM
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const menuOverlay = document.getElementById('menuOverlay');
    const body = document.body;
    
    // Verificar que todos los elementos existan
    if (!menuToggle) {
        console.error('❌ Elemento menuToggle no encontrado');
        return;
    }
    if (!sidebar) {
        console.error('❌ Elemento sidebar no encontrado');
        return;
    }
    if (!menuOverlay) {
        console.error('❌ Elemento menuOverlay no encontrado');
        return;
    }
    
    console.log('✅ Todos los elementos del menú encontrados');
    
    // Estado del menú
    let isMenuOpen = false;
    
    // Función para abrir el menú
    function openMenu() {
        console.log('🟢 Abriendo menú...');
        isMenuOpen = true;
        sidebar.classList.add('menu-open');
        menuOverlay.classList.add('active');
        body.classList.add('no-scroll');
        menuToggle.classList.add('active');
        
        console.log('✅ Menú abierto - Classes:', sidebar.className);
    }
    
    // Función para cerrar el menú
    function closeMenu() {
        console.log('🔴 Cerrando menú...');
        isMenuOpen = false;
        sidebar.classList.remove('menu-open');
        menuOverlay.classList.remove('active');
        body.classList.remove('no-scroll');
        menuToggle.classList.remove('active');
        
        console.log('✅ Menú cerrado - Classes:', sidebar.className);
    }
    
    // Función para alternar el menú
    function toggleMenu() {
        console.log('🔄 Alternando menú... Estado actual:', isMenuOpen ? 'ABIERTO' : 'CERRADO');
        if (isMenuOpen) {
            closeMenu();
        } else {
            openMenu();
        }
    }
    
    // Event listener para el botón hamburguesa
    menuToggle.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('🍔 Click en botón hamburguesa');
        
        // Solo funcionar en móviles
        if (window.innerWidth <= 768) {
            toggleMenu();
        } else {
            console.log('⚠️ Click ignorado - no estamos en móvil');
        }
    });
    
    // Event listener para el overlay
    menuOverlay.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('🖱️ Click en overlay - cerrando menú');
        closeMenu();
    });
    
    // Cerrar menú con tecla ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isMenuOpen) {
            console.log('⌨️ ESC presionado - cerrando menú');
            closeMenu();
        }
    });
    
    // Manejar cambios de tamaño de ventana
    window.addEventListener('resize', function() {
        const width = window.innerWidth;
        console.log('📐 Resize detectado - Nueva anchura:', width);
        
        if (width > 768) {
            // En escritorio, asegurar que el menú esté cerrado
            if (isMenuOpen) {
                console.log('🖥️ Cambiando a escritorio - cerrando menú');
                closeMenu();
            }
        }
    });
    
    // Prevenir clicks en enlaces del menú cuando está cerrado en móvil
    const menuLinks = sidebar.querySelectorAll('a');
    menuLinks.forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768 && isMenuOpen) {
                // En móvil, cerrar el menú después de hacer click en un enlace
                setTimeout(closeMenu, 100);
            }
        });
    });
    
    // Funciones globales para debugging
    window.debugMenu = function() {
        console.log('📊 Estado del menú:');
        console.log('- Anchura ventana:', window.innerWidth);
        console.log('- Menú abierto:', isMenuOpen);
        console.log('- Clases sidebar:', sidebar.className);
        console.log('- Clases overlay:', menuOverlay.className);
        console.log('- Clases body:', body.className);
        console.log('- Transform sidebar:', getComputedStyle(sidebar).transform);
        console.log('- Display overlay:', getComputedStyle(menuOverlay).display);
    };
    
    window.testMenu = function() {
        console.log('🧪 Probando menú...');
        toggleMenu();
    };
    
    window.forceOpenMenu = function() {
        console.log('🔓 Forzando apertura del menú...');
        openMenu();
    };
    
    window.forceCloseMenu = function() {
        console.log('🔒 Forzando cierre del menú...');
        closeMenu();
    };
    
    // Inicialización completa
    console.log('✅ Dashboard JS inicializado correctamente');
    console.log('💡 Funciones disponibles en consola:');
    console.log('   - debugMenu() - Ver estado del menú');
    console.log('   - testMenu() - Alternar menú');
    console.log('   - forceOpenMenu() - Abrir forzado');
    console.log('   - forceCloseMenu() - Cerrar forzado');
    
    // Estado inicial
    debugMenu();
});