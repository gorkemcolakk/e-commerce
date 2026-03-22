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
    document.body.classList.toggle('light-mode', t === 'light');
    document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: t } }));
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
    const ctrls = document.querySelectorAll('.user-controls');
    
    ctrls.forEach(ctrl => {
        if (token && user) {
            const firstName = user.fullname.split(' ')[0];
            const dashBase = user.role === 'admin' ? 'admin.html' : user.role === 'organizer' ? 'organizer.html' : 'dashboard.html';
            
            let dropLinks = '';
            const commonLinks = `
              <hr style="border:0; border-top:1px solid var(--border); margin:4px 0;">
              <a href="dashboard.html?tab=tickets" class="dropdown-item">🎟 Biletlerim</a>
              <a href="dashboard.html?tab=wishlist" class="dropdown-item">❤ Favorilerim</a>
              <a href="dashboard.html?tab=notifications" class="dropdown-item">🔔 Bildirimler</a>
            `;

            if (user.role === 'admin') {
              dropLinks = `
                <a href="admin.html?tab=pending" class="dropdown-item">⏳ Onay Bekleyenler</a>
                <a href="admin.html?tab=users" class="dropdown-item">👥 Kullanıcılar</a>
                <a href="admin.html?tab=allevents" class="dropdown-item">📋 Tüm Etkinlikler</a>
                <a href="admin.html?tab=revenue" class="dropdown-item">💰 Platform Geliri</a>
                ${commonLinks}
              `;
            } else if (user.role === 'organizer') {
              dropLinks = `
                <a href="organizer.html?tab=myevents" class="dropdown-item">🎪 Etkinliklerim</a>
                <a href="organizer.html?tab=create" class="dropdown-item">➕ Etkinlik Oluştur</a>
                <a href="organizer.html?tab=revenue" class="dropdown-item">💰 Gelir Raporu</a>
                <a href="organizer.html?tab=promotions" class="dropdown-item">🎫 Promosyonlar</a>
                <a href="organizer.html?tab=validate" class="dropdown-item">🔍 QR Doğrulama</a>
                ${commonLinks}
              `;
            } else {
              dropLinks = `
                <a href="dashboard.html?tab=tickets" class="dropdown-item">🎟 Biletlerim</a>
                <a href="dashboard.html?tab=wishlist" class="dropdown-item">❤ Favorilerim</a>
                <a href="dashboard.html?tab=notifications" class="dropdown-item">🔔 Bildirimler</a>
              `;
            }

            ctrl.innerHTML = `
              ${THEME_BTN}
              <div class="user-dropdown-wrapper">
                <div style="display:flex; align-items:center; gap:8px;">
                  <a href="${dashBase}?tab=profile" class="btn btn-outline" style="font-size:.85rem;display:flex;align-items:center;gap:6px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                    ${firstName}
                  </a>
                  <button class="btn btn-outline" style="padding: 8px; font-size: 1.1rem;" onclick="event.stopPropagation(); window.toggleUserDropdown()">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                  </button>
                </div>
                <div id="userDropdown" class="user-dropdown-menu">
                  ${dropLinks}
                  <hr style="border:0; border-top:1px solid var(--border); margin:4px 0;">
                  <button onclick="logout()" class="dropdown-item" style="width:100%; border:0; background:none; cursor:pointer; color:var(--coral); text-align:left;">🚪 Çıkış Yap</button>
                </div>
              </div>`;
        } else {
            ctrl.innerHTML = `${THEME_BTN}
              <a href="login.html" class="btn btn-outline" style="font-size:.85rem;">Giriş Yap</a>
              <a href="register.html" class="btn btn-primary" style="font-size:.85rem;">Kayıt Ol</a>`;
        }
    });

    // Handle dropdown closing
    window.toggleUserDropdown = () => {
        const menu = document.getElementById('userDropdown');
        if (menu) menu.classList.toggle('active');
    };

    document.addEventListener('click', () => {
        document.getElementById('userDropdown')?.classList.remove('active');
    });
    // Ensure theme toggle is present even if .user-controls is missing
    if (ctrls.length === 0) {
        if (!document.querySelector('.theme-toggle')) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = THEME_BTN;
            const btn = wrapper.firstElementChild;
            
            const navC = document.querySelector('.navbar .container');
            if (navC) {
                btn.style.marginLeft = 'auto'; // push to the right
                navC.appendChild(btn);
            } else {
                // No navbar exists (e.g. login/register), float it top right
                btn.style.position = 'absolute';
                btn.style.top = '25px';
                btn.style.right = '25px';
                btn.style.zIndex = '9999';
                btn.style.background = 'var(--bg-card)';
                btn.style.border = '1px solid var(--border-color)';
                btn.style.borderRadius = '50%';
                btn.style.width = '42px';
                btn.style.height = '42px';
                btn.style.display = 'flex';
                btn.style.alignItems = 'center';
                btn.style.justifyContent = 'center';
                btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)';
                document.body.appendChild(btn);
            }
        }
    }
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
        const password = document.getElementById('password').value;
        if (password.length < 6) {
          setFeedback(form, 'Şifre en az 6 karakter olmalıdır', 'error');
          btn.textContent = orig; btn.disabled = false;
          return;
        }
        const role = document.getElementById('role')?.value || 'customer';
        try {
            const r = await fetch('/api/auth/register', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    fullname: `${document.getElementById('firstName').value} ${document.getElementById('lastName').value}`,
                    phone: document.getElementById('phone').value,
                    birthdate: document.getElementById('birthdate').value,
                    email: document.getElementById('email').value,
                    password: password, role
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
    loadWishlistIds();
    loadNotifBadge();
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
    const form = document.getElementById('loginForm');

    // loginForm yoksa bu sayfa login sayfası değildir
    if (!form) return;

    if (resetToken) {
        // Başlıkları güncelle
        const title = document.querySelector('.auth-title');
        const subtitle = document.querySelector('.auth-subtitle');
        if (title) title.textContent = 'Şifre Sıfırlama';
        if (subtitle) subtitle.textContent = 'Yeni şifrenizi belirleyin.';

        form.innerHTML = `
            <div class="form-group">
                <label class="form-label">Yeni Şifre</label>
                <div class="password-input-wrapper">
                    <input type="password" id="new_password" class="form-control" placeholder="••••••••" required minlength="6">
                    <button type="button" class="password-toggle" onclick="togglePassword('new_password')">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                    </button>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Yeni Şifre (Tekrar)</label>
                <div class="password-input-wrapper">
                    <input type="password" id="new_password_confirm" class="form-control" placeholder="••••••••" required minlength="6">
                </div>
            </div>
            <button type="submit" class="btn btn-primary auth-submit">Şifreyi Güncelle</button>
        `;

        // Social login ve divider'ı gizle
        document.querySelectorAll('.social-login-grid, .auth-divider').forEach(g => g.style.display = 'none');

        // Düğmeyi değiştirerek eski event listener'ları temizle
        const newForm = form.cloneNode(true);
        form.parentNode.replaceChild(newForm, form);

        newForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = newForm.querySelector('button[type="submit"]');
            const orig = btn.textContent;
            const newPass = newForm.querySelector('#new_password').value;
            const confirmPass = newForm.querySelector('#new_password_confirm').value;

            if (newPass.length < 6) {
                setFeedback(newForm, 'Şifre en az 6 karakter olmalıdır!', 'error');
                return;
            }

            if (newPass !== confirmPass) {
                setFeedback(newForm, 'Şifreler eşleşmiyor!', 'error');
                return;
            }

            btn.textContent = 'Güncelleniyor...';
            btn.disabled = true;
            try {
                const res = await fetch('/api/auth/reset-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: resetToken, new_password: newPass})
                });
                const d = await res.json();
                if (res.ok) {
                    setFeedback(newForm, 'Şifreniz güncellendi! Giriş sayfasına yönlendiriliyorsunuz...', 'success');
                    setTimeout(() => { window.location.href = 'login.html'; }, 2000);
                } else {
                    setFeedback(newForm, d.message || 'Hata oluştu. Token süresi dolmuş olabilir.', 'error');
                    btn.textContent = orig;
                    btn.disabled = false;
                }
            } catch (err) {
                setFeedback(newForm, 'Sunucu bağlantı hatası', 'error');
                btn.textContent = orig;
                btn.disabled = false;
            }
        });
        return;
    }

    // "Şifremi Unuttum" bağlantısını işle
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
                .catch(() => alert('Bir hata oluştu. Lütfen tekrar deneyin.'));
            }
        };
    }
}

// Password toggle
window.togglePassword = id => {
    const el = document.getElementById(id);
    el.type = el.type === 'password' ? 'text' : 'password';
};
