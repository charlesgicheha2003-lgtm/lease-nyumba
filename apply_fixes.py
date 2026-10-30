#!/usr/bin/env python3
"""Applies all Leasity fixes. Usage: python3 apply_fixes.py index.html
Writes index.fixed.html next to the original (original is untouched)."""
import re, sys

src = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
s = open(src, encoding='utf-8').read()

def sub(pat, new, count=1, name=''):
    global s
    s, n = re.subn(pat, (lambda m: new(m)) if callable(new) else (lambda m: new), s, count=count, flags=re.S)
    print(('OK   ' if n else 'MISS ') + (name or pat[:55]))

def lit(old, new, name=''):
    sub(re.escape(old), new, count=0, name=name or old[:55])

# ---------- CSS: print only the receipt when a receipt is open ----------
sub(r"@media print \{.*?\n    \}\n  </style>", r'''@media print {
      body.print-receipt * { visibility: hidden; }
      body.print-receipt #receiptPrintModalContent,
      body.print-receipt #receiptPrintModalContent * { visibility: visible; }
      body.print-receipt #receiptPrintModalContent { position: absolute; left: 0; top: 0; width: 100%; margin: 0; padding: 20px; box-shadow: none !important; border: none !important; }
    }
  </style>''', name='print CSS')

# ---------- HTML ----------
lit('<option value="OVERDUE">Overdue</option>',
    '<option value="OVERDUE">Overdue</option>\n              <option value="APPROACHING">Approaching Due</option>\n              <option value="NOT_DUE">Not Yet Due</option>', 'status filter options')
lit('Within next 60 days', 'Cycles ending within 10 days')
lit('<select id="payTenantSelect" required', '<select id="payTenantSelect" onchange="prefillPayAmount()" required')
lit('>Reset Cycle</button>', '>Set End Day</button>')

# ---------- JS: helpers, safe storage, settings ----------
sub(r"// Local Storage Mock Data", r'''// ---- Helpers ----
    const load = k => { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } };
    const _settings = load('leasity_settings') || {};
    let currency = _settings.currency || 'KSh';
    let company = _settings.company || 'Leasity Properties Ltd';
    const ADMIN_TABS = ['expenses', 'reports', 'settings'];
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const fmtDate = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

    // Due date info for the current month (clamped to month length, compared at midnight)
    function getDueInfo(t) {
      const today = new Date(); today.setHours(0,0,0,0);
      const dim = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
      const dueDate = new Date(today.getFullYear(), today.getMonth(), Math.min(Number(t.dueDay) || 5, dim));
      const diffDays = Math.round((dueDate - today) / 86400000); // >0 upcoming, 0 today, <0 late
      return { dueDate, diffDays, daysLate: Math.max(0, -diffDays) };
    }
    function daysToCycleEnd(t) { return (Number(t.leaseEnd) || 31) - new Date().getDate(); }

    function applyRole() {
      const admin = activeRole === 'admin';
      document.querySelectorAll('.role-admin').forEach(el => el.classList.toggle('hidden', !admin));
    }
    function setTodayDefaults() {
      const today = fmtDate(new Date());
      ['payDate', 'expDate'].forEach(id => { const el = document.getElementById(id); if (el) el.value = today; });
    }
    function loadSettingsUI() {
      document.getElementById('settingCompanyName').value = company;
      document.getElementById('settingCurrency').value = currency;
    }
    function prefillPayAmount() {
      const sel = document.getElementById('payTenantSelect');
      const t = tenants.find(x => x.id === Number(sel.value));
      if (!t) return;
      const bal = Math.max(0, Number(t.rent) - getTenantPaidThisMonth(t.id));
      document.getElementById('payAmount').value = bal > 0 ? bal : t.rent;
    }

    // Local Storage Mock Data''', name='helpers block')

sub(r"JSON\.parse\(localStorage\.getItem\('(leasity_\w+)'\)\)", lambda m: f"load('{m.group(1)}')", count=0, name='safe localStorage load')
sub(r"function saveData\(\) \{", "function saveData() { try { _save(); } catch (e) { console.warn('Storage unavailable', e); } }\n    function _save() {", name='saveData try/catch')
sub(r"refreshAll\(\);\s*\};", "loadSettingsUI();\n      setTodayDefaults();\n      refreshAll();\n    };", name='onload defaults')

# ---------- Status / due logic ----------
sub(r"function updateBadges\(\) \{.*?\n    \}\n", r'''function updateBadges() {
      let expiringCount = 0, overdueCount = 0;
      tenants.forEach(t => {
        const d = daysToCycleEnd(t);
        if (d >= 0 && d <= 10) expiringCount++;
        if (getTenantStatus(t) === 'OVERDUE') overdueCount++;
      });
      const lb = document.getElementById('leaseExpiringBadgeNav'); if (lb) lb.innerText = expiringCount;
      const ob = document.getElementById('overdueBadgeNav'); if (ob) ob.innerText = overdueCount;
    }
''', name='updateBadges')

sub(r"function getTenantStatus\(t\) \{.*?\n    \}\n", r'''function getTenantStatus(t) {
      if (getTenantPaidThisMonth(t.id) >= Number(t.rent)) return 'PAID';
      const { diffDays } = getDueInfo(t);
      if (diffDays < 0) return 'OVERDUE';
      if (diffDays <= 3) return 'APPROACHING';   // includes "due today"
      return 'NOT_DUE';
    }
''', name='getTenantStatus')

sub(r"const pDate = new Date\(p\.date\);\s*if\(pDate\.getMonth\(\) === currentMonth && pDate\.getFullYear\(\) === currentYear\) \{",
    "const [py, pm] = String(p.date).split('-').map(Number);\n          if(pm - 1 === currentMonth && py === currentYear) {", name='timezone-safe payment month')

sub(r"refreshAll\(\) \{.*?updateBadges\(\);", lambda m: m.group(0) + "\n      applyRole();", name='applyRole in refreshAll')

# ---------- Roles / tabs ----------
sub(r"function setActiveRole\(role\) \{.*?\n    \}\n", r'''function setActiveRole(role) {
      activeRole = role;
      closeModal('roleModal');
      const admin = role === 'admin';
      document.getElementById('roleBadgeLabel').innerText = admin ? 'Landlord (Admin)' : 'Caretaker / Manager';
      document.getElementById('sidebarRoleDisplay').innerText = admin ? 'Landlord (Full Access)' : 'Caretaker (Limited Access)';
      applyRole();
      if (!admin && ADMIN_TABS.includes(currentTab)) switchTab('dashboard');
      showToast(`Switched view to ${admin ? 'Landlord (Admin)' : 'Caretaker / Manager'}`, 'info');
    }
''', name='setActiveRole')
sub(r"function switchTab\(tabId\) \{\s*currentTab = tabId;",
    "function switchTab(tabId) {\n      if (activeRole !== 'admin' && ADMIN_TABS.includes(tabId)) tabId = 'dashboard';\n      currentTab = tabId;", name='switchTab guard')
sub(r'<div class="(bg-slate-50 p-3 rounded-lg border border-slate-100)">(\s*<span class="text-slate-400 block text-\[10px\] uppercase">(?:Expenses|Net Profit)</span>)',
    lambda m: f'<div class="role-admin {m.group(1)}">{m.group(2)}', count=0, name='hide P&L cards from caretaker')

# ---------- Dashboard ----------
sub(r"let notDueCount = 0;", "let notDueCount = 0;\n      let overdueAmount = 0;", name='overdueAmount var')
sub(r"else if\(status === 'OVERDUE'\) overdueCount\+\+;",
    "else if(status === 'OVERDUE') { overdueCount++; overdueAmount += Math.max(0, Number(t.rent) - paid); }", name='overdueAmount sum')
sub(r"const leaseEnd = new Date\(t\.leaseEnd\);\s*const daysToExpiry = Math\.ceil\(\(leaseEnd - now\) / \(1000 \* 60 \* 60 \* 24\)\);\s*if\(daysToExpiry >= 0 && daysToExpiry <= 60\) \{",
    "const daysToExpiry = daysToCycleEnd(t);\n        if(daysToExpiry >= 0 && daysToExpiry <= 10) {", name='dashboard expiry logic')
lit("const outstanding = Math.max(0, totalExpected - totalCollected);", "const outstanding = overdueAmount;")
lit("${expiringCount} Leases", "${expiringCount} Cycles")
lit("lease(s) expiring within 60 days", "rent cycle(s) ending within 10 days")

# ---------- Overdue + reminders ----------
sub(r"const dueDay = t\.dueDay \|\| 5;\s*const dueDate = new Date\(now\.getFullYear\(\), now\.getMonth\(\), dueDay\);\s*if\(now > dueDate\) \{\s*const daysLate = .*?\n\s*overdueList\.push\(.*?\);\s*\}",
    "const di = getDueInfo(t);\n          if(di.diffDays < 0) {\n            overdueList.push({ tenant: t, balance, dueDate: fmtDate(di.dueDate), daysLate: di.daysLate });\n          }", name='overdue table logic')
sub(r"const dueDay = t\.dueDay \|\| 5;\s*const dueDate = new Date\(now\.getFullYear\(\), now\.getMonth\(\), dueDay\);\s*const diffDays = Math\.ceil\(\(dueDate - now\) / \(1000 \* 60 \* 60 \* 24\)\);",
    "const { diffDays, daysLate } = getDueInfo(t);", name='reminder due logic')
lit("currentReminderType === 'overdue' && now > dueDate", "currentReminderType === 'overdue' && diffDays < 0")
sub(r"\s*const daysLate = Math\.ceil\(\(now - dueDate\) / \(1000 \* 60 \* 60 \* 24\)\);", "", name='remove stale daysLate')
lit("const cleanPhone = t.phone.replace(/[^0-9]/g, '');",
    "let cleanPhone = t.phone.replace(/[^0-9]/g, '');\n      if (cleanPhone.startsWith('0')) cleanPhone = '254' + cleanPhone.slice(1);")

# ---------- Lease cycle action ----------
sub(r"function renewLease\(tenantId\) \{.*?\n    \}\n", r'''function renewLease(tenantId) {
      const t = tenants.find(x => x.id === tenantId);
      if (!t) return;
      const v = prompt(`New rent end day (1-31) for ${t.name}:`, t.leaseEnd || 31);
      if (v === null) return;
      const d = Number(v);
      if (!Number.isInteger(d) || d < 1 || d > 31) { showToast('Enter a whole day between 1 and 31', 'info'); return; }
      t.leaseEnd = d;
      saveData(); refreshAll();
      showToast(`Rent end day updated for ${t.name}`, 'success');
    }
''', name='renewLease')

# ---------- Receipts / printing ----------
sub(r"const balance = t \? Math\.max\(0, Number\(t\.rent\) - getTenantPaidThisMonth\(t\.id\)\) : 0;",
    r'''// Balance as at the time of THIS payment (same month, payments up to and including it)
      const balance = t ? Math.max(0, Number(t.rent) - payments
        .filter(x => x.tenantId === t.id && String(x.date).slice(0,7) === String(p.date).slice(0,7) && (x.date < p.date || (x.date === p.date && x.id <= p.id)))
        .reduce((sum, x) => sum + Number(x.amount), 0)) : 0;''', name='receipt balance')
lit("openModal('receiptModal');", "document.body.classList.add('print-receipt');\n      openModal('receiptModal');")
sub(r"function closeModal\(id\) \{\s*document\.getElementById\(id\)\.classList\.add\('hidden'\);",
    "function closeModal(id) {\n      document.getElementById(id).classList.add('hidden');\n      if (id === 'receiptModal') document.body.classList.remove('print-receipt');", name='closeModal')
sub(r"function openModal\(id\) \{\s*document\.getElementById\(id\)\.classList\.remove\('hidden'\);",
    "function openModal(id) {\n      document.getElementById(id).classList.remove('hidden');\n      if (id === 'recordPaymentModal') setTimeout(prefillPayAmount, 0);", name='openModal prefill')

# ---------- Forms ----------
sub(r"const rctNum = `RCT-2026-.*?;",
    "const nextNo = Math.max(0, ...payments.map(x => parseInt(String(x.id).split('-').pop(), 10) || 0)) + 1;\n      const rctNum = `RCT-${new Date().getFullYear()}-${String(nextNo).padStart(3, '0')}`;", name='receipt numbering')
lit("document.getElementById('paymentForm').reset();", "document.getElementById('paymentForm').reset();\n      setTodayDefaults();")
lit("document.getElementById('expenseForm').reset();", "document.getElementById('expenseForm').reset();\n      setTodayDefaults();")
sub(r"(const leaseEnd = Number\(document\.getElementById\('tenantLeaseEnd'\)\.value\);)\s*\n\s*if\(editId\) \{",
    lambda m: m.group(1) + r'''

      const dup = tenants.some(x => String(x.id) !== String(editId) &&
        x.property.trim().toLowerCase() === property.trim().toLowerCase() &&
        x.unit.trim().toLowerCase() === unit.trim().toLowerCase());
      if (dup) { showToast('That unit already has a tenant.', 'info'); return; }

      if(editId) {''', name='duplicate unit check')
lit("confirm('Are you sure you want to delete this tenant?')", "confirm('Delete this tenant? Their past payments stay in the ledger as \"Former Tenant\".')")
lit("Unknown Tenant", "Former Tenant")

# ---------- Settings & currency ----------
sub(r"function saveSettings\(\) \{.*?\n    \}\n", r'''function saveSettings() {
      currency = document.getElementById('settingCurrency').value.trim() || 'KSh';
      company = document.getElementById('settingCompanyName').value.trim() || 'Leasity Properties Ltd';
      try { localStorage.setItem('leasity_settings', JSON.stringify({ currency, company })); } catch (e) {}
      refreshAll();
      showToast('Settings saved successfully!', 'success');
    }
''', name='saveSettings')
sub(r"KSh \$\{", "${currency} ${", count=0, name='dynamic currency')

# ---------- Security: HTML escaping ----------
lit("filterTenantsByProperty('${p.name}')", "filterTenantsByProperty(decodeURIComponent('${encodeURIComponent(p.name)}'))")
lit('<option value="${p}">${p}</option>', '<option value="${esc(p)}">${esc(p)}</option>')
sub(r"\$\{(t|e|p)\.(name|property|unit|phone|ref|method|desc|category)\}", lambda m: "${esc(%s.%s)}" % (m.group(1), m.group(2)), count=0, name='escape user fields')
sub(r"\$\{(tName|tUnit)\}", lambda m: "${esc(%s)}" % m.group(1), count=0, name='escape tName/tUnit')
# WhatsApp text is plain text, not HTML: undo escaping inside that function
sub(r"function sendWhatsAppReminder.*?\n    \}\n", lambda m: re.sub(r"\$\{esc\(((?:t)\.\w+)\)\}", r"${\1}", m.group(0)), name='unescape WhatsApp message')
# Toast: render message as text
lit('toast.innerHTML = `<i class="fa-solid ${icon} text-base"></i><span>${message}</span>`;',
    'toast.innerHTML = `<i class="fa-solid ${icon} text-base"></i><span></span>`;\n      toast.querySelector(\'span\').textContent = message;')
# CSV: '#' and other characters break encodeURI data URLs
lit("const encodedUri = encodeURI(csvContent);",
    "const encodedUri = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csvContent.replace('data:text/csv;charset=utf-8,', ''));")

out = src.rsplit('.', 1)[0] + '.fixed.html'
open(out, 'w', encoding='utf-8').write(s)
print('\nWritten:', out, '- any "MISS" lines above mean that patch did not match your file.')
