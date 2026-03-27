// Global navbar and footer injector
// Add <div id="navbar"></div> and <div id="footer"></div> in each HTML page

(function () {
    // Detect current page for active link
    const path = window.location.pathname;

    const navLinks = [
        { href: '/',              label: 'Home' },
        { href: '/route-planner', label: 'Route Planner' },
        { href: '/model-info',    label: 'Model Info' },
    ];

    const navHTML = `
        <nav class="navbar">
            <div class="container">
                <div class="nav-brand">
                    <span class="nav-icon">🌱</span>
                    <span class="nav-title">EcoRoute AI</span>
                </div>
                <ul class="nav-menu">
                    ${navLinks.map(l => `
                        <li><a href="${l.href}" class="nav-link ${path === l.href ? 'active' : ''}">${l.label}</a></li>
                    `).join('')}
                </ul>
            </div>
        </nav>`;

    const footerHTML = `
        <footer>
            <div class="container">
                <div class="footer-content">
                    <div class="footer-links">
                        <a href="/docs" class="footer-link" target="_blank">📚 API Docs</a>
                        <a href="/health" class="footer-link" target="_blank">🏥 Health Check</a>
                    </div>
                    <div class="footer-status">
                        <span class="status-dot" id="statusDot"></span>
                        <span id="statusText">Checking status...</span>
                    </div>
                </div>
            </div>
        </footer>`;

    // Inject navbar
    const navEl = document.getElementById('navbar');
    if (navEl) navEl.outerHTML = navHTML;

    // Inject footer
    const footerEl = document.getElementById('footer');
    if (footerEl) footerEl.outerHTML = footerHTML;

    // Health check
    fetch('/health')
        .then(r => r.json())
        .then(d => {
            const dot = document.getElementById('statusDot');
            const txt = document.getElementById('statusText');
            if (!dot || !txt) return;
            if (d.status === 'healthy') {
                txt.textContent = 'All Systems Operational';
            } else {
                dot.classList.add('error');
                txt.textContent = 'System Issues Detected';
            }
        })
        .catch(() => {
            const dot = document.getElementById('statusDot');
            const txt = document.getElementById('statusText');
            if (dot) dot.classList.add('error');
            if (txt) txt.textContent = 'Unable to Check Status';
        });
})();
