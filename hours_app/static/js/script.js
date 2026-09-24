document.addEventListener('DOMContentLoaded', () => {

    const body = document.body;
    const darkModeToggle = document.getElementById('toggle-dark-mode');
    const DARK_MODE_KEY = 'darkMode';

    // Restore dark mode preference
    if(localStorage.getItem(DARK_MODE_KEY) === 'enabled'){
        body.classList.add('dark-mode');
        body.classList.remove('light-mode');
    }

    // Toggle dark mode
    if(darkModeToggle){
        darkModeToggle.addEventListener('click', e => {
            e.preventDefault();
            const isDark = body.classList.toggle('dark-mode');
            body.classList.toggle('light-mode', !isDark);
            localStorage.setItem(DARK_MODE_KEY, isDark ? 'enabled' : 'disabled');
        });
    }

    // Active navbar link
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link.nav-button');
    navLinks.forEach(link => {
        link.classList.toggle('active', link.href === window.location.href);
    });

    // Check In/Out form autosave
    const form = document.getElementById('check-form');
    if(!form) return;

    const reasonField = document.getElementById('reason');
    const progressFill = document.getElementById('progress-fill');
    const FORM_REASON_KEY = 'formReason';

    if(!reasonField || !progressFill) return;

    const updateProgress = () => {
        const hasText = reasonField.value.trim().length > 0;
        progressFill.style.width = hasText ? '100%' : '0%';
        localStorage.setItem(FORM_REASON_KEY, reasonField.value);
    };

    reasonField.value = localStorage.getItem(FORM_REASON_KEY) || '';
    updateProgress();
    reasonField.addEventListener('input', updateProgress);

});
