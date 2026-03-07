/* ─── RevendAI Panel — app.js ─────────────────────────────────────────────── */

// ─── Event delegation for table action buttons ────────────────────────────────
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const id = btn.dataset.id;
  const name = btn.dataset.name;
  const slug = btn.dataset.slug;

  console.log('[Event] Action:', action, 'ID:', id, 'Slug:', slug);

  if (action === 'edit') openEditModal(id);
  else if (action === 'delete') openDeleteModal(id, name);
  else if (action === 'redeploy') doRedeploy(id, btn);
  else if (action === 'show-urls') openUrlsModal(slug);
});

// ─── Toast notifications ──────────────────────────────────────────────────────

function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const icons = { success: '✓', error: '✗', info: 'ℹ' };
  toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'opacity 0.3s, transform 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ─── Modal helpers ────────────────────────────────────────────────────────────

function openModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.add('active');
}

function closeModal(id) {
  const overlay = document.getElementById(id);
  if (overlay) overlay.classList.remove('active');
}

// Close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.remove('active');
  });
});

// Close on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
  }
});

// ─── API helpers ──────────────────────────────────────────────────────────────

async function apiRequest(method, url, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(url, opts);
  if (res.status === 204) return null;

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Erro ${res.status}`);
  }
  return data;
}

// ─── Status badge helper ──────────────────────────────────────────────────────

function statusBadge(status) {
  const labels = { running: 'Rodando', error: 'Erro', pending: 'Pendente' };
  const label = labels[status] || status;
  return `<span class="status-badge status-${status}">${label}</span>`;
}

// ─── Date formatter (São Paulo) ───────────────────────────────────────────────

function formatDate(isoString) {
  if (!isoString) return '<span style="color:var(--text-muted)">—</span>';
  try {
    const d = new Date(isoString);
    console.log('[formatDate] Input:', isoString, 'Parsed:', d);
    const formatted = d.toLocaleString('pt-BR', {
      timeZone: 'America/Sao_Paulo',
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
    console.log('[formatDate] Formatted:', formatted);
    return formatted;
  } catch (err) {
    console.error('[formatDate] Error:', err, 'Input:', isoString);
    return isoString;
  }
}

// ─── Render table row ─────────────────────────────────────────────────────────

function renderRow(client) {
  return `
    <tr id="row-${client.id}">
      <td>
        <div class="client-name">${escHtml(client.name)}</div>
        <div class="client-slug">${escHtml(client.slug)}</div>
      </td>
      <td><span class="parser-badge">${escHtml(client.parser_used || 'unknown')}</span></td>
      <td>${statusBadge(client.status)}</td>
      <td><span class="updated-at">${formatDate(client.last_updated_at)}</span></td>
      <td class="base-url-cell">
        <button class="btn btn-sm btn-secondary" title="Ver URLs da API"
          data-action="show-urls" data-slug="${escHtml(client.slug)}">📋 URLs</button>
      </td>
      <td class="actions-cell">
        <button class="btn btn-icon btn-sm" title="Editar"
          data-action="edit" data-id="${client.id}">✏️</button>
        <button class="btn btn-icon btn-sm" title="Excluir"
          data-action="delete" data-id="${client.id}" data-name="${escHtml(client.name)}">🗑️</button>
        <button class="btn btn-icon btn-sm" title="Redeploy"
          data-action="redeploy" data-id="${client.id}">🔄</button>
      </td>
    </tr>`;
}

function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Update row in table ──────────────────────────────────────────────────────

function updateRow(client) {
  const row = document.getElementById(`row-${client.id}`);
  if (row) {
    row.outerHTML = renderRow(client);
  }
}

function addRow(client) {
  const tbody = document.getElementById('clients-tbody');
  const emptyState = document.getElementById('empty-state');
  if (emptyState) emptyState.remove();
  tbody.insertAdjacentHTML('beforeend', renderRow(client));
  updateCount(1);
}

function removeRow(clientId) {
  const row = document.getElementById(`row-${clientId}`);
  if (row) row.remove();
  updateCount(-1);
  const tbody = document.getElementById('clients-tbody');
  if (tbody && tbody.children.length === 0) {
    tbody.innerHTML = `
      <tr id="empty-state">
        <td colspan="6">
          <div class="empty-state">
            <div class="empty-icon">🔌</div>
            <h3>Nenhuma API cadastrada</h3>
            <p>Clique em "Nova API" para começar</p>
          </div>
        </td>
      </tr>`;
  }
}

function updateCount(delta) {
  const el = document.getElementById('clients-count');
  if (el) {
    const current = parseInt(el.textContent) || 0;
    el.textContent = Math.max(0, current + delta);
  }
}

// ─── Create API ───────────────────────────────────────────────────────────────

document.getElementById('form-create')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('[type=submit]');
  const name = document.getElementById('create-name').value.trim();
  const source_url = document.getElementById('create-url').value.trim();

  if (!name || !source_url) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Criando...';

  try {
    const client = await apiRequest('POST', '/admin/clients', { name, source_url });
    closeModal('modal-create');
    e.target.reset();
    addRow(client);
    showToast(`API "${client.name}" criada! Deploy em andamento...`, 'success');

    // Poll for status update
    pollClientStatus(client.id);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Criar API';
  }
});

// ─── Edit API ─────────────────────────────────────────────────────────────────

let editingClientId = null;

function openEditModal(clientId) {
  editingClientId = clientId;
  const row = document.getElementById(`row-${clientId}`);
  if (!row) return;

  // Extract current values from row
  const name = row.querySelector('.client-name')?.textContent || '';
  document.getElementById('edit-name').value = name;
  document.getElementById('edit-url').value = '';

  // Fetch current data from server
  apiRequest('GET', '/admin/clients').then(clients => {
    const client = clients.find(c => c.id === clientId);
    if (client) {
      document.getElementById('edit-name').value = client.name;
      document.getElementById('edit-url').value = client.source_url;
    }
  }).catch(() => {});

  openModal('modal-edit');
}

document.getElementById('form-edit')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!editingClientId) return;

  const btn = e.target.querySelector('[type=submit]');
  const name = document.getElementById('edit-name').value.trim();
  const source_url = document.getElementById('edit-url').value.trim();

  if (!name || !source_url) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Salvando...';

  try {
    const client = await apiRequest('PUT', `/admin/clients/${editingClientId}`, { name, source_url });
    closeModal('modal-edit');
    updateRow(client);
    showToast(`API "${client.name}" atualizada!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar';
  }
});

// Redeploy button inside edit modal
document.getElementById('btn-edit-redeploy')?.addEventListener('click', async () => {
  if (!editingClientId) return;
  const btn = document.getElementById('btn-edit-redeploy');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Iniciando...';
  try {
    await apiRequest('POST', `/admin/clients/${editingClientId}/redeploy`);
    showToast('Redeploy iniciado!', 'success');
    closeModal('modal-edit');
    pollClientStatus(editingClientId);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔄 Redeploy';
  }
});

// ─── Delete API ───────────────────────────────────────────────────────────────

let deletingClientId = null;

function openDeleteModal(clientId, clientName) {
  deletingClientId = clientId;
  const nameEl = document.getElementById('delete-client-name');
  if (nameEl) nameEl.textContent = clientName;
  openModal('modal-delete');
}

// ─── URLs Modal ───────────────────────────────────────────────────────────────

function openUrlsModal(slug) {
  console.log('[openUrlsModal] Called with slug:', slug);
  console.log('[openUrlsModal] BASE_URL:', window.BASE_URL);
  
  const externalUrl = `${window.BASE_URL}/${slug}/api/data`;
  const internalUrl = `http://api_revendai:3000/${slug}/api/data`;
  
  console.log('[openUrlsModal] External URL:', externalUrl);
  console.log('[openUrlsModal] Internal URL:', internalUrl);
  
  const externalEl = document.getElementById('url-external');
  const internalEl = document.getElementById('url-internal');
  
  console.log('[openUrlsModal] External element:', externalEl);
  console.log('[openUrlsModal] Internal element:', internalEl);
  
  if (externalEl) externalEl.textContent = externalUrl;
  if (internalEl) internalEl.textContent = internalUrl;
  
  openModal('modal-urls');
}

async function copyUrl(type) {
  const urlId = type === 'external' ? 'url-external' : 'url-internal';
  const urlElement = document.getElementById(urlId);
  const url = urlElement.textContent;
  
  try {
    await navigator.clipboard.writeText(url);
    showToast('URL copiada para área de transferência!', 'success', 2000);
  } catch (err) {
    // Fallback para navegadores antigos
    const textArea = document.createElement('textarea');
    textArea.value = url;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      showToast('URL copiada para área de transferência!', 'success', 2000);
    } catch (err2) {
      showToast('Erro ao copiar URL', 'error');
    }
    document.body.removeChild(textArea);
  }
}

document.getElementById('btn-confirm-delete')?.addEventListener('click', async () => {
  if (!deletingClientId) return;
  const btn = document.getElementById('btn-confirm-delete');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Excluindo...';

  try {
    await apiRequest('DELETE', `/admin/clients/${deletingClientId}`);
    closeModal('modal-delete');
    removeRow(deletingClientId);
    showToast('API excluída com sucesso', 'success');
    deletingClientId = null;
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Excluir';
  }
});

// ─── Redeploy ─────────────────────────────────────────────────────────────────

async function doRedeploy(clientId, btn) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';

  try {
    const res = await apiRequest('POST', `/admin/clients/${clientId}/redeploy`);
    showToast(res.message || 'Redeploy iniciado!', 'success');
    pollClientStatus(clientId);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

// ─── Status polling ───────────────────────────────────────────────────────────

function pollClientStatus(clientId, maxAttempts = 30, interval = 3000) {
  let attempts = 0;

  const poll = async () => {
    attempts++;
    try {
      const clients = await apiRequest('GET', '/admin/clients');
      const client = clients.find(c => c.id === clientId);
      if (client) {
        updateRow(client);
        if (client.status === 'running' || client.status === 'error') {
          if (client.status === 'running') {
            showToast(`✓ "${client.name}" atualizado: ${client.vehicle_count} veículos`, 'success');
          } else {
            showToast(`✗ Erro no deploy de "${client.name}": ${client.last_error}`, 'error', 8000);
          }
          return; // Stop polling
        }
      }
    } catch {}

    if (attempts < maxAttempts) {
      setTimeout(poll, interval);
    }
  };

  setTimeout(poll, interval);
}

// ─── Init ─────────────────────────────────────────────────────────────────────

// Auto-poll pending clients on page load
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-status="pending"]').forEach(el => {
    const clientId = el.closest('tr')?.id?.replace('row-', '');
    if (clientId) pollClientStatus(clientId);
  });
});
