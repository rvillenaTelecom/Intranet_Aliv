// Sidebar toggle (colapsar/expandir en escritorio)
const sidebar = document.getElementById('sidebar');
const toggle = document.getElementById('sidebarToggle');
if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    });
    if (localStorage.getItem('sidebarCollapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }
}

// Sidebar como menú deslizable en móvil/tablet (≤900px)
const MOBILE_BREAKPOINT = 900;
const mobileMenuBtn = document.getElementById('mobileMenuBtn');
const sidebarBackdrop = document.getElementById('sidebarBackdrop');

function closeMobileSidebar() {
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (sidebarBackdrop) sidebarBackdrop.classList.remove('active');
}
function openMobileSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('collapsed'); // en móvil siempre se ve completo, con texto
    sidebar.classList.add('mobile-open');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('active');
}
if (mobileMenuBtn && sidebar) {
    mobileMenuBtn.addEventListener('click', () => {
        if (sidebar.classList.contains('mobile-open')) closeMobileSidebar();
        else openMobileSidebar();
    });
}
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeMobileSidebar);
document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', () => {
        if (window.innerWidth <= MOBILE_BREAKPOINT) closeMobileSidebar();
    });
});
window.addEventListener('resize', () => {
    if (window.innerWidth > MOBILE_BREAKPOINT) closeMobileSidebar();
});

// Date display
const dateEl = document.getElementById('currentDate');
if (dateEl) {
    const now = new Date();
    const opts = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateEl.textContent = now.toLocaleDateString('es-PE', opts);
}

// Password toggle for login
const pwdInput = document.getElementById('password');
const pwdToggle = document.getElementById('pwdToggle');
if (pwdToggle && pwdInput) {
    pwdToggle.addEventListener('click', () => {
        const isText = pwdInput.type === 'text';
        pwdInput.type = isText ? 'password' : 'text';
        pwdToggle.className = isText ? 'fa-solid fa-eye input-icon' : 'fa-solid fa-eye-slash input-icon';
    });
}