/* Lógica compartilhada do shell admin: toggle do drawer no mobile,
   fechamento por backdrop e gesture de swipe (4.7).
   Carregado por templates/cadastros/admin_shell.html. */
(function () {
    var sidebar = document.getElementById('adminSidebar');
    var backdrop = document.getElementById('adminSidebarBackdrop');
    var toggle = document.getElementById('adminMenuToggle');

    if (!sidebar) return;

    function closeSidebar() {
        sidebar.classList.remove('show');
        if (backdrop) backdrop.classList.remove('show');
        document.body.classList.remove('admin-sidebar-open');
    }
    function openSidebar() {
        sidebar.classList.add('show');
        if (backdrop) backdrop.classList.add('show');
        document.body.classList.add('admin-sidebar-open');
    }

    if (toggle) {
        toggle.addEventListener('click', function () {
            if (sidebar.classList.contains('show')) closeSidebar();
            else openSidebar();
        });
    }
    if (backdrop) backdrop.addEventListener('click', closeSidebar);

    window.addEventListener('resize', function () {
        if (window.innerWidth >= 992) closeSidebar();
    });
    sidebar.querySelectorAll('a').forEach(function (a) {
        a.addEventListener('click', function () {
            if (window.innerWidth < 992) closeSidebar();
        });
    });

    // ----- 4.7: swipe para fechar a sidebar (mobile) -----
    var startX = null;
    var startY = null;
    var tracking = false;
    var SWIPE_THRESHOLD_PX = 60;          // distância mínima
    var DIRECTION_LOCK_RATIO = 1.4;       // |dx| > |dy| * 1.4 = horizontal

    sidebar.addEventListener('touchstart', function (e) {
        if (window.innerWidth >= 992) return;
        if (!sidebar.classList.contains('show')) return;
        if (e.touches.length !== 1) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        tracking = true;
    }, { passive: true });

    sidebar.addEventListener('touchmove', function (e) {
        if (!tracking) return;
        var t = e.touches[0];
        var dx = t.clientX - startX;
        var dy = t.clientY - startY;
        // Cancela se o gesto vira vertical (scroll)
        if (Math.abs(dy) > Math.abs(dx) * DIRECTION_LOCK_RATIO) {
            tracking = false;
        }
    }, { passive: true });

    sidebar.addEventListener('touchend', function (e) {
        if (!tracking) return;
        tracking = false;
        var endX = (e.changedTouches[0] || {}).clientX;
        if (endX == null) return;
        var dx = endX - startX;
        // Sidebar abre da esquerda → fechar = arrasto para a esquerda (dx negativo)
        if (dx <= -SWIPE_THRESHOLD_PX) {
            closeSidebar();
        }
    }, { passive: true });
})();
