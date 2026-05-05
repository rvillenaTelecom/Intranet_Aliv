// Sidebar toggle
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