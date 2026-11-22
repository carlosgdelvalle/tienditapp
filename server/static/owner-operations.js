'use strict';

window.ownerOperations = ({api, status, requestError, money, quantity, scaledInput, session, formatDate}) => {
  const $ = id => document.getElementById(id);
  const pendingLabel = 'Se interrumpió la respuesta. Confirma el registro pendiente antes de iniciar otro.';
  const readVersion = new Map();
  const writes = new Set();
  let adjustment;
  let customer;
  let teamMember;
  let adjustmentTrigger;
  let teamTrigger;

  function asQuantity(milli, unit) {
    const label = unit === 'pieza' && milli !== 1000 ? 'piezas' : unit;
    return quantity.format(milli / 1000) + ' ' + label;
  }

  function record(title, detail, button) {
    const row = document.createElement('li');
    const heading = document.createElement('div');
    heading.className = 'record-title';
    const label = document.createElement('strong');
    label.textContent = title;
    heading.append(label);
    if (button) heading.append(button);
    const description = document.createElement('small');
    description.textContent = detail;
    row.append(heading, description);
    return row;
  }

  function actionButton(text, label, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary';
    button.textContent = text;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', handler);
    return button;
  }

  async function loadSection(section, endpoint, draw) {
    const identity = session();
    const version = (readVersion.get(section) || 0) + 1;
    readVersion.set(section, version);
    $('refresh-' + section).disabled = true;
    status(section + '-status', 'Cargando…');
    try {
      const data = await api(endpoint);
      if (session() !== identity || readVersion.get(section) !== version) return;
      status(section + '-status', '');
      draw(data);
      return true;
    } catch (error) {
      if (session() === identity && readVersion.get(section) === version) {
        requestError(section + '-status', error, 'No se pudo actualizar. Intenta de nuevo.');
      }
    } finally {
      if (readVersion.get(section) === version) $('refresh-' + section).disabled = false;
    }
  }

  function pendingKey(section) {
    return 'abarpay.owner.operation.' + session().tenantId + '.' + section;
  }

  function pending(section) {
    try { return JSON.parse(sessionStorage.getItem(pendingKey(section))); }
    catch (_) { return null; }
  }

  async function submit(section, statusId, input, refresh, syncControls) {
    const identity = session();
    if (!identity || writes.has(section)) return;
    const storageKey = pendingKey(section);
    const saved = pending(section);
    const attempt = saved || {...input, key: crypto.randomUUID()};
    if (!attempt.url) return;
    try {
      if (!saved) sessionStorage.setItem(storageKey, JSON.stringify(attempt));
    } catch (_) {
      status(statusId, 'El navegador no pudo guardar el intento. Revisa su configuración.', true);
      return;
    }
    writes.add(section);
    syncControls();
    status(statusId, 'Guardando…');
    try {
      await api(attempt.url, {method: attempt.method || 'POST', body: attempt.body, key: attempt.key});
      sessionStorage.removeItem(storageKey);
      if (session() !== identity) return;
      status(statusId, 'Guardado.');
      await refresh();
    } catch (error) {
      if (session() !== identity) return;
      if ([400, 404, 409, 422].includes(error.status)) {
        sessionStorage.removeItem(storageKey);
        status(statusId, error.message, true);
        if (section === 'inventory' && error.status === 409) {
          adjustment = null;
          await loadInventory();
          status('inventory-status', 'La existencia cambió. Selecciona el producto y vuelve a confirmar el conteo.', true);
          $('inventory-status').tabIndex = -1;
          $('inventory-status').focus();
        }
      } else requestError(statusId, error, pendingLabel);
    } finally {
      writes.delete(section);
      if (session() === identity) syncControls();
    }
  }

  function syncAdjustment() {
    const saved = pending('inventory');
    $('adjust-panel').hidden = !saved && !adjustment;
    $('adjust-form').hidden = !!saved || !adjustment;
    $('retry-inventory').hidden = !saved;
    $('retry-inventory').disabled = writes.has('inventory');
    if (saved) {
      $('adjust-label').textContent = saved.label;
      if (!writes.has('inventory') && !$('adjust-status').textContent) status('adjust-status', pendingLabel, true);
    }
  }

  async function loadInventory() {
    syncAdjustment();
    return loadSection('inventory', '/api/owner/inventory', data => {
      $('inventory-items').replaceChildren(...data.items.map(item => {
        const stock = item.unlimitedStock ? 'Existencia ilimitada' : asQuantity(item.stockMilli, item.unit);
        const button = item.unlimitedStock ? null : actionButton('Ajustar', 'Ajustar ' + item.name, event => {
          if (pending('inventory')) {
            syncAdjustment();
            $('retry-inventory').focus();
            return;
          }
          adjustment = item;
          adjustmentTrigger = event.currentTarget;
          $('adjust-label').textContent = item.name + ' · Actual: ' + stock;
          $('adjust-stock').value = String(item.stockMilli / 1000);
          $('adjust-reason').value = '';
          status('adjust-status', '');
          syncAdjustment();
          $('adjust-stock').focus();
        });
        const row = record(item.name, stock, button);
        row.dataset.productId = item.id;
        row.dataset.stockMilli = item.stockMilli;
        return row;
      }));
      $('inventory-movements').replaceChildren(...data.movements.map(entry => {
        const change = (entry.deltaMilli > 0 ? '+' : '') + quantity.format(entry.deltaMilli / 1000);
        const reason = {sale: 'Venta', sale_oversell: 'Faltante por venta sin conexión'}[entry.reason] || entry.reason;
        return record(entry.name + ' · ' + change, reason +
          ' · ' + formatDate(entry.createdAt));
      }));
      $('inventory-movements-empty').hidden = data.movements.length > 0;
      if (adjustment && !pending('inventory') &&
          data.items.find(item => item.id === adjustment.id)?.stockMilli !== adjustment.stockMilli) {
        adjustment = null;
        syncAdjustment();
        status('inventory-status', 'La existencia cambió. Vuelve a seleccionar el producto y confirma el conteo.', true);
      } else if (!data.items.length) {
        status('inventory-status', 'Agrega productos en Catálogo para ver sus existencias.');
      }
    });
  }

  function saveAdjustment(input) {
    return submit('inventory', 'adjust-status', input, async () => {
      adjustment = null;
      if (await loadInventory()) status('inventory-status', 'Existencia confirmada.');
    }, syncAdjustment);
  }

  $('adjust-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!adjustment) return;
    const stockMilli = scaledInput('adjust-stock', 3);
    const reason = $('adjust-reason').value.trim();
    if (stockMilli === null || stockMilli > 2147483647 || !reason) {
      status('adjust-status', 'Revisa la existencia contada y escribe el motivo.', true);
      return;
    }
    saveAdjustment({
      url: '/api/owner/inventory/' + adjustment.id + '/adjust',
      label: adjustment.name + ' · Conteo: ' + asQuantity(stockMilli, adjustment.unit),
      body: {stockMilli, expectedStockMilli: adjustment.stockMilli, reason},
    });
  });
  $('cancel-adjust').addEventListener('click', () => {
    adjustment = null;
    syncAdjustment();
    (adjustmentTrigger?.isConnected ? adjustmentTrigger : $('refresh-inventory')).focus();
  });
  $('retry-inventory').addEventListener('click', () => saveAdjustment());
  $('refresh-inventory').addEventListener('click', loadInventory);

  function syncForm(section, formId, statusId) {
    const saved = pending(section);
    $(formId).hidden = !!saved;
    $('retry-' + section).hidden = !saved;
    $('retry-' + section).disabled = writes.has(section);
    if (saved && !writes.has(section) && !$(statusId).textContent) {
      status(statusId, saved.label + ' · ' + pendingLabel, true);
    }
    return saved;
  }

  function syncCustomerForm() {
    syncForm('customer', 'customer-form', 'customer-status');
  }

  function syncFiadoForm() {
    const saved = syncForm('fiado', 'fiado-entry-form', 'fiado-entry-status');
    $('fiado-detail').hidden = !saved && !customer;
    $('refresh-fiado-detail').hidden = !customer;
    if (!customer) {
      $('fiado-customer').textContent = saved?.label || '';
      $('fiado-balance').textContent = '';
      $('fiado-entries').replaceChildren();
    }
    return saved;
  }

  function balanceLabel(cents) {
    return cents < 0 ? 'Saldo a favor ' + money(-cents) : 'Saldo pendiente ' + money(cents);
  }

  function loadFiado() {
    syncCustomerForm();
    syncFiadoForm();
    return loadSection('fiado', '/api/owner/fiado/customers', data => {
      $('fiado-items').replaceChildren(...data.items.map(item => record(
        item.name,
        balanceLabel(item.balanceCents),
        actionButton('Ver cuenta', 'Ver cuenta de ' + item.name, () => openCustomer(item)),
      )));
      if (!data.items.length) status('fiado-status', 'Todavía no hay clientes de fiado.');
    });
  }

  function openCustomer(item) {
    if (writes.has('fiado')) return;
    const attempt = pending('fiado');
    if (attempt && attempt.url !== customerRoute(item) + '/entries') {
      syncFiadoForm();
      $('retry-fiado').focus();
      return;
    }
    if (item.id !== customer?.id) {
      $('fiado-entry-form').reset();
      $('fiado-entries').replaceChildren();
      status('fiado-entry-status', '');
    }
    customer = item;
    $('fiado-customer').textContent = item.name;
    $('fiado-balance').textContent = '';
    syncFiadoForm();
    $('fiado-customer').tabIndex = -1;
    $('fiado-customer').focus();
    loadCustomer();
  }

  function customerRoute(item) {
    return '/api/owner/fiado/customers/' + item.id;
  }

  function loadCustomer() {
    if (!customer) return;
    return loadSection('fiado-detail', customerRoute(customer), data => {
      $('fiado-balance').textContent = balanceLabel(data.balanceCents);
      $('fiado-entries').replaceChildren(...data.items.map(entry => {
        const kind = entry.kind === 'payment' ? 'Abono' : 'Cargo';
        return record(kind + ' · ' + money(entry.amountCents), [entry.note, formatDate(entry.createdAt)].filter(Boolean).join(' · '));
      }));
      if (!data.items.length) status('fiado-detail-status', 'Todavía no hay movimientos.');
    });
  }

  function amountAndNote(prefix, statusId) {
    const amountCents = scaledInput(prefix + '-amount', 2);
    const note = $(prefix + '-note').value.trim();
    if (!amountCents || amountCents > 2147483647 || !note) {
      status(statusId, 'Escribe un importe mayor que cero y un concepto.', true);
      return null;
    }
    return {amountCents, note};
  }

  function saveCustomer(input) {
    return submit('customer', 'customer-status', input, async () => {
      $('customer-form').reset();
      await loadFiado();
    }, syncCustomerForm);
  }

  function saveFiado(input) {
    return submit('fiado', 'fiado-entry-status', input, async () => {
      $('fiado-entry-form').reset();
      await Promise.all([loadFiado(), loadCustomer()]);
    }, syncFiadoForm);
  }

  $('customer-form').addEventListener('submit', event => {
    event.preventDefault();
    const name = $('customer-name').value.trim();
    if (!name) { status('customer-status', 'Escribe el nombre del cliente.', true); return; }
    saveCustomer({url: '/api/owner/fiado/customers', label: name, body: {name}});
  });
  $('fiado-entry-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!customer) return;
    const payment = amountAndNote('fiado', 'fiado-entry-status');
    if (payment) saveFiado({
      url: customerRoute(customer) + '/entries', label: customer.name + ' · ' + money(payment.amountCents),
      body: {...payment, kind: $('fiado-kind').value},
    });
  });
  $('retry-customer').addEventListener('click', () => saveCustomer());
  $('retry-fiado').addEventListener('click', () => saveFiado());
  $('refresh-fiado').addEventListener('click', loadFiado);
  $('refresh-fiado-detail').addEventListener('click', loadCustomer);

  function syncExpenseForm() {
    syncForm('expenses', 'expense-form', 'expense-status');
  }

  function loadExpenses() {
    syncExpenseForm();
    return loadSection('expenses', '/api/owner/expenses', data => {
      $('expenses-total').textContent = 'Total registrado ' + money(data.totalCents);
      $('expenses-items').replaceChildren(...data.items.map(entry => record(
        entry.note || 'Gasto', money(entry.amountCents) + ' · ' + formatDate(entry.createdAt),
      )));
      if (!data.items.length) status('expenses-status', 'Todavía no hay gastos.');
    });
  }

  function saveExpense(input) {
    return submit('expenses', 'expense-status', input, async () => {
      $('expense-form').reset();
      await loadExpenses();
    }, syncExpenseForm);
  }

  $('expense-form').addEventListener('submit', event => {
    event.preventDefault();
    const body = amountAndNote('expense', 'expense-status');
    if (body) saveExpense({
      url: '/api/owner/expenses', label: body.note + ' · ' + money(body.amountCents), body,
    });
  });
  $('retry-expenses').addEventListener('click', () => saveExpense());
  $('refresh-expenses').addEventListener('click', loadExpenses);

  const teamFields = {
    'team-sell': 'canSell', 'team-fiado': 'canFiado',
    'team-inventory': 'canInventory', 'team-active': 'active',
  };
  const memberName = item => item.name || item.email || (item.role === 'owner' ? 'Dueño de la tienda' : 'Persona vinculada');

  function syncTeam() {
    const saved = syncForm('team', 'team-form', 'team-edit-status');
    $('team-editor').hidden = !saved && !teamMember;
    if (saved) $('team-member').textContent = saved.label;
  }

  function loadTeam() {
    syncTeam();
    return loadSection('team', '/api/tenant/members', data => {
      $('team-items').replaceChildren(...data.items.map(item => {
        const name = memberName(item);
        const role = item.role === 'owner' ? 'Dueño' : 'Empleado';
        const details = [role, item.active ? 'Acceso activo' : 'Acceso suspendido'];
        if (item.role !== 'owner') {
          const permissions = [item.canSell && 'Cobrar', item.canFiado && 'Fiar', item.canInventory && 'Ajustar inventario']
            .filter(Boolean);
          details.push(permissions.length ? permissions.join(', ') : 'Sin permisos de operación');
        }
        const edit = item.role === 'owner' ? null : actionButton('Editar permisos', 'Editar permisos de ' + name, event => {
          if (pending('team')) { syncTeam(); $('retry-team').focus(); return; }
          teamMember = item;
          teamTrigger = event.currentTarget;
          $('team-member').textContent = name;
          status('team-edit-status', '');
          for (const [field, key] of Object.entries(teamFields)) $(field).checked = item[key];
          syncTeam();
          $('team-sell').focus();
        });
        return record(name, details.join(' · '), edit);
      }));
    });
  }

  function saveTeam(input) {
    return submit('team', 'team-edit-status', input, async () => {
      teamMember = null;
      if (await loadTeam()) status('team-status', 'Permisos guardados.');
    }, syncTeam);
  }

  $('team-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!teamMember) return;
    const body = Object.fromEntries(Object.entries(teamFields).map(([field, key]) => [key, $(field).checked]));
    saveTeam({url: '/api/tenant/members/' + teamMember.userId, method: 'PATCH', label: memberName(teamMember), body});
  });
  $('retry-team').addEventListener('click', () => saveTeam());
  $('cancel-team').addEventListener('click', () => {
    teamMember = null;
    syncTeam();
    (teamTrigger?.isConnected ? teamTrigger : $('refresh-team')).focus();
  });
  $('refresh-team').addEventListener('click', loadTeam);

  function clearInviteLink() {
    $('team-invite-result').hidden = true;
    $('team-invite-url').value = '';
    $('team-invite-expiry').textContent = '';
  }

  $('team-invite-form').addEventListener('submit', async event => {
    event.preventDefault();
    const identity = session();
    const button = $('create-team-invite');
    if (!identity || button.disabled) return;
    const digits = $('team-invite-phone').value.replace(/\D/g, '');
    const phone = digits.length === 12 && digits.startsWith('52') ? digits.slice(2) : digits;
    if (phone.length !== 10) {
      status('team-invite-status', 'Escribe un número mexicano de 10 dígitos.', true);
      return;
    }
    const body = {
      phone, canSell: $('invite-sell').checked, canFiado: $('invite-fiado').checked,
      canInventory: $('invite-inventory').checked,
    };
    const controls = [...event.currentTarget.elements];
    for (const control of controls) control.disabled = true;
    clearInviteLink();
    status('team-invite-status', 'Preparando la invitación…');
    try {
      const invite = await api('/api/tenant/members/invite', {method: 'POST', body});
      if (session() !== identity) return;
      $('team-invite-url').value = new URL('/invite/' + encodeURIComponent(invite.token), location.origin).href;
      $('team-invite-expiry').textContent = invite.expiresAt ? 'Vence el ' + formatDate(invite.expiresAt) : '';
      $('team-invite-result').hidden = false;
      $('team-invite-form').reset();
      status('team-invite-status', 'Invitación lista. Comparte el enlace con la persona invitada.');
    } catch (error) {
      if (session() === identity) requestError('team-invite-status', error, 'No se pudo confirmar la invitación. Intenta de nuevo.');
    } finally {
      for (const control of controls) control.disabled = false;
    }
  });

  $('copy-team-invite').addEventListener('click', async () => {
    const field = $('team-invite-url');
    try {
      await navigator.clipboard.writeText(field.value);
      status('team-invite-status', 'Enlace copiado.');
    } catch (_) {
      field.select();
      status('team-invite-status', 'Copia el enlace seleccionado.');
    }
  });

  const sections = {inventario: loadInventory, fiado: loadFiado, gastos: loadExpenses, equipo: loadTeam};
  return {
    load(section) {
      sections[section]?.();
    },
    reset() {
      adjustment = null;
      customer = null;
      teamMember = null;
      clearInviteLink();
      for (const id of ['adjust-panel', 'fiado-detail', 'team-editor']) $(id).hidden = true;
      for (const id of ['inventory-items', 'inventory-movements', 'fiado-items', 'fiado-entries', 'expenses-items',
        'team-items', 'expenses-total']) $(id).replaceChildren();
      for (const id of ['adjust-status', 'customer-status', 'fiado-entry-status', 'expense-status', 'team-edit-status',
        'team-invite-status']) status(id, '');
      for (const id of ['adjust-form', 'customer-form', 'fiado-entry-form', 'expense-form', 'team-form', 'team-invite-form']) $(id).reset();
    },
  };
};
