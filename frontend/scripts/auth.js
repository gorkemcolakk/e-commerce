/* ─── EVENTİX auth.js — unified auth + theme ─── */
const API_BASE = '';

const getToken   = () => localStorage.getItem('token');
const getUser    = () => JSON.parse(localStorage.getItem('user') || 'null');
const authHeaders = () => ({
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${getToken()}`
});

// ── ROUTE HELPERS ────────────────────────────────────────────
window.goToLogin = () => { window.location.href = 'login.html'; };
window.goToDashboard = () => {
    const u = getUser();
    if (!u) return goToLogin();
    window.location.href =
        u.role === 'admin'      ? 'admin.html'     :
        u.role === 'organizer'  ? 'organizer.html' : 'dashboard.html';
};
window.logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = 'index.html';
};

// ── THEME ─────────────────────────────────────────────────────
function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('eventix-theme', t);
}
window.toggleTheme = () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(cur === 'light' ? 'dark' : 'light');
};
// Apply immediately (no flash)
applyTheme(localStorage.getItem('eventix-theme') || 'dark');

// ── NAV RENDER ───────────────────────────────────────────────
const THEME_BTN = `
  <button class="theme-toggle" onclick="toggleTheme()" title="Tema" aria-label="Toggle theme">
    <svg class="icon-moon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
    <svg class="icon-sun"  width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
  </button>`;

function renderNav() {
    const token = getToken(), user = getUser();
    document.querySelectorAll('.user-controls').forEach(ctrl => {
        if (token && user) {
            const href = user.role === 'admin' ? 'admin.html' : user.role === 'organizer' ? 'organizer.html' : 'dashboard.html';
            ctrl.innerHTML = `${THEME_BTN}
              <a href="${href}" class="btn btn-outline" style="font-size:.85rem;display:flex;align-items:center;gap:6px;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                ${user.fullname.split(' ')[0]}
              </a>
              <button onclick="logout()" class="btn btn-primary" style="font-size:.85rem;">Çıkış</button>`;
        } else {
            ctrl.innerHTML = `${THEME_BTN}
              <a href="login.html" class="btn btn-outline" style="font-size:.85rem;">Giriş Yap</a>
              <a href="register.html" class="btn btn-primary" style="font-size:.85rem;">Kayıt Ol</a>`;
        }
    });
}

// ── WISHLIST ──────────────────────────────────────────────────
let wishlistIds = new Set();

async function loadWishlistIds() {
    if (!getToken()) return;
    try {
        const r = await fetch('/api/wishlist', { headers: authHeaders() });
        if (r.ok) wishlistIds = new Set((await r.json()).map(e => e.id));
    } catch {}
}

window.toggleWishlist = async (eventId, btn) => {
    if (!getToken()) { alert('Favorilere eklemek için giriş yapmalısınız.'); return goToLogin(); }
    const inList = wishlistIds.has(eventId);
    try {
        const r = await fetch(`/api/wishlist/${eventId}`, { method: inList ? 'DELETE' : 'POST', headers: authHeaders() });
        if (r.ok) {
            if (inList) { wishlistIds.delete(eventId); btn.classList.remove('wished'); }
            else        { wishlistIds.add(eventId);    btn.classList.add('wished');    }
        }
    } catch {}
};

// ── NOTIFICATIONS BADGE ───────────────────────────────────────
async function loadNotifBadge() {
    if (!getToken()) return;
    try {
        const r = await fetch('/api/notifications', { headers: authHeaders() });
        if (r.ok) {
            const unread = (await r.json()).filter(n => !n.is_read).length;
            document.querySelectorAll('.notif-badge').forEach(b => {
                b.style.display = unread > 0 ? 'inline-flex' : 'none';
                b.textContent = unread > 9 ? '9+' : unread;
            });
        }
    } catch {}
}

// ── TOAST ─────────────────────────────────────────────────────
window.showToast = (msg, type = 'default') => {
    document.querySelector('.toast')?.remove();
    const t = Object.assign(document.createElement('div'), { className: `toast ${type}`, innerHTML: msg });
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 400); }, 3200);
};

// ── FORMS ─────────────────────────────────────────────────────
function initLoginForm() {
    const form = document.getElementById('loginForm');
    if (!form) return;
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = form.querySelector('[type=submit]'), orig = btn.textContent;
        btn.textContent = 'Giriş yapılıyor...'; btn.disabled = true;
        try {
            const r = await fetch('/api/auth/login', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: document.getElementById('email').value, password: document.getElementById('password').value })
            });
            const d = await r.json();
            if (r.ok) {
                localStorage.setItem('token', d.token);
                localStorage.setItem('user', JSON.stringify(d.user));
                window.location.href = d.user.role === 'admin' ? 'admin.html' : d.user.role === 'organizer' ? 'organizer.html' : 'index.html';
            } else { setFeedback(form, d.message || 'Giriş başarısız', 'error'); btn.textContent = orig; btn.disabled = false; }
        } catch { setFeedback(form, 'Sunucuya bağlanılamadı', 'error'); btn.textContent = orig; btn.disabled = false; }
    });
}

function initRegisterForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;
    form.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = form.querySelector('[type=submit]'), orig = btn.textContent;
        btn.textContent = 'Hesap oluşturuluyor...'; btn.disabled = true;
        const role = document.getElementById('role')?.value || 'customer';
        try {
            const r = await fetch('/api/auth/register', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    fullname: `${document.getElementById('firstName').value} ${document.getElementById('lastName').value}`,
                    email: document.getElementById('email').value,
                    password: document.getElementById('password').value, role
                })
            });
            const d = await r.json();
            if (r.ok) { setFeedback(form, 'Kayıt başarılı! Yönlendiriliyorsunuz...', 'success'); setTimeout(() => { window.location.href = 'login.html'; }, 1500); }
            else { setFeedback(form, d.message || 'Kayıt başarısız', 'error'); btn.textContent = orig; btn.disabled = false; }
        } catch { setFeedback(form, 'Sunucuya bağlanılamadı', 'error'); btn.textContent = orig; btn.disabled = false; }
    });
}

function setFeedback(form, msg, type) {
    let el = form.querySelector('.form-feedback');
    if (!el) { el = document.createElement('div'); el.className = 'form-feedback'; form.prepend(el); }
    el.className = `form-feedback auth-alert ${type}`;
    el.textContent = (type === 'error' ? '⚠ ' : '✓ ') + msg;
}

// ── INIT ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    renderNav();
    initLoginForm();
    initRegisterForm();
    initPasswordReset();
    window.addEventListener('scroll', () => {
        document.querySelector('.navbar')?.classList.toggle('scrolled', window.scrollY > 40);
    });
    const mobileOverlay = document.getElementById('mobileNav');
    document.getElementById('mobileMenuBtn')?.addEventListener('click', () => mobileOverlay?.classList.add('active'));
    document.getElementById('closeMobileMenu')?.addEventListener('click', () => mobileOverlay?.classList.remove('active'));
});

// Password Reset Flow
function initPasswordReset() {
    const params = new URLSearchParams(window.location.search);
    const resetToken = params.get('reset_token');
    if (resetToken && window.location.pathname.includes('login.html')) {
        document.querySelector('.auth-title').textContent = 'Şifre Sıfırlama';
        document.querySelector('.auth-subtitle').textContent = 'Yeni şifrenizi belirleyin.';
        const form = document.getElementById('loginForm');
        form.innerHTML = `
            <div class="form-group">
                <label class="form-label">Yeni Şifre</label>
                <div class="password-input-wrapper">
                    <input type="password" id="new_password" class="form-control" placeholder="••••••••" required>
                </div>
            </div>
            <button type="submit" class="btn btn-primary auth-submit">Şifreyi Güncelle</button>
        `;
        const grids = document.querySelectorAll('.social-login-grid, .auth-divider');
        grids.forEach(g => g.style.display = 'none');
        
        // Remove old submit listener by replacing form or just overriding onsubmit?
        // Let's replace the node to clear listeners
        const newForm = form.cloneNode(true);
        form.parentNode.replaceChild(newForm, form);
        
        newForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = newForm.querySelector('button');
            const orig = btn.textContent;
            btn.textContent = 'Güncelleniyor...';
            btn.disabled = true;
            try {
                const res = await fetch('/api/auth/reset-password', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: resetToken, new_password: newForm.querySelector('#new_password').value})
                });
                const d = await res.json();
                if (res.ok) {
                    alert('Şifreniz güncellendi, lütfen yeni şifrenizle giriş yapın.');
                    window.location.href = 'login.html';
                } else {
                    alert(d.message || 'Hata oluştu');
                    btn.textContent = orig; btn.disabled = false;
                }
            } catch (err) { alert('Hata oluştu'); btn.textContent = orig; btn.disabled = false; }
        });
        return;
    }

    // Attach to "Şifremi Unuttum" link
    const forgotLink = document.querySelector('.forgot-password');
    if (forgotLink) {
        forgotLink.onclick = (e) => {
            e.preventDefault();
            const email = prompt('Şifre sıfırlama linki almak için kayıtlı e-posta adresinizi girin:');
            if (email) {
                fetch('/api/auth/forgot-password', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                })
                .then(r => r.json())
                .then(d => alert(d.message || 'Başarılı'))
                .catch(err => alert('Bir hata oluştu. Lütfen tekrar deneyin.'));
            }
        };
    }
}

// Password toggle
window.togglePassword = id => {
    const el = document.getElementById(id);
    el.type = el.type === 'password' ? 'text' : 'password';
};
