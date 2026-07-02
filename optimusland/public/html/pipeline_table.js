(function() {
  var container = root_element ? root_element.querySelector('.pipeline-container') : null;
  if (!container) return;

  var contentEl = container.querySelector('#pipeline-content');
  var fromInput = container.querySelector('#filter-from');
  var toInput = container.querySelector('#filter-to');
  var supplierInput = container.querySelector('#filter-supplier');
  var customerInput = container.querySelector('#filter-customer');
  var refreshBtn = container.querySelector('#btn-refresh');
  var autoToggle = container.querySelector('#toggle-auto');
  var lastRefreshedEl = container.querySelector('#last-refreshed');
  var autoInterval = null;

  function setDefaultDates() {
    var today = new Date();
    var thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    var fmt = function(d) { return d.toISOString().split('T')[0]; };
    if (!fromInput.value) fromInput.value = fmt(thirtyDaysAgo);
    if (!toInput.value) toInput.value = fmt(today);
  }

  function statusClass(status) {
    if (!status) return 'status-info';
    var s = status.toLowerCase();
    if (['completed','submitted','closed','paid'].indexOf(s) !== -1) return 'status-ok';
    if (['draft','not started'].indexOf(s) !== -1) return 'status-warning';
    if (['failed','cancelled','overdue'].indexOf(s) !== -1) return 'status-critical';
    return 'status-info';
  }

  function statusBadge(status) {
    var cls = statusClass(status);
    return '<span class="status-badge ' + cls + '"><span class="dot"></span>' + (status || 'N/A') + '</span>';
  }

  function entityLink(name, doctype) {
    if (!name) return '<span class="status-badge status-info">--</span>';
    return '<a class="entity-link" onclick="frappe.set_route(\'Form\', \'' + doctype + '\', \'' + name + '\')">' + name + '</a>';
  }

  function renderTier(data, icon, title, cols, rowRenderer) {
    if (!data || data.length === 0) {
      return '<div class="tier-section"><div class="tier-header"><span class="tier-icon">' + icon + '</span><span class="tier-title">' + title + '</span><span class="tier-count">0 items</span></div></div>';
    }
    var headerRow = cols.map(function(c) { return '<th>' + c + '</th>'; }).join('');
    var bodyRows = data.map(function(row) {
      return '<tr>' + rowRenderer(row).map(function(c) { return '<td>' + c + '</td>'; }).join('') + '</tr>';
    }).join('');
    return '<div class="tier-section"><div class="tier-header" onclick="this.classList.toggle(\'collapsed\'); this.nextElementSibling.classList.toggle(\'collapsed\')"><span class="tier-icon">' + icon + '</span><span class="tier-title">' + title + '</span><span class="tier-count">' + data.length + ' item' + (data.length !== 1 ? 's' : '') + '</span><span class="tier-chevron">&#9660;</span></div><div class="tier-body"><table class="pipeline-table"><thead><tr>' + headerRow + '</tr></thead><tbody>' + bodyRows + '</tbody></table></div></div>';
  }

  function renderSourcing(data) {
    return renderTier(data, '&#128668;', 'Sourcing - Weight Slip - Batch - PR',
      ['PR','Date','Supplier','Item','Qty','Rate','Batch','Weight Slip','PP Status'],
      function(row) {
        return [entityLink(row.pr,'Purchase Receipt'), row.pr_date || '--', row.pr_supplier || '--', row.item_code || '--', row.qty ? Number(row.qty).toLocaleString() : '--', row.rate ? '\u20AC' + Number(row.rate).toFixed(2) : '--', entityLink(row.batch_no,'Batch'), entityLink(row.weight_slip,'Weight Slip'), row.production_plan ? entityLink(row.production_plan,'Production Plan') : statusBadge('No PP')];
      }
    );
  }

  function renderManufacturing(data) {
    return renderTier(data, '&#127981;', 'Manufacturing - PR - PP - WO - SE',
      ['PR','Production Plan','PP Status','Work Order','WO Status','Qty','Produced','BOM','SE Transfer','SE Manufacture'],
      function(row) {
        return [entityLink(row.pr,'Purchase Receipt'), entityLink(row.pp,'Production Plan'), statusBadge(row.pp_status), entityLink(row.wo,'Work Order'), statusBadge(row.wo_status), row.wo_qty ? Number(row.wo_qty).toLocaleString() : '--', row.wo_produced_qty ? Number(row.wo_produced_qty).toLocaleString() : '0', row.wo_bom || '--', entityLink(row.se_transfer,'Stock Entry'), entityLink(row.se_manufacture,'Stock Entry')];
      }
    );
  }

  function renderFulfillment(data) {
    return renderTier(data, '&#128230;', 'Fulfillment - DN - SI - PI',
      ['DN','Date','Customer','DN Status','Billed','SI','SI Status','PI','PI Status','Item','Batch','Qty'],
      function(row) {
        return [entityLink(row.dn,'Delivery Note'), row.dn_date || '--', row.customer || '--', statusBadge(row.dn_status), row.per_billed ? Number(row.per_billed).toFixed(0) + '%' : '0%', entityLink(row.si,'Sales Invoice'), statusBadge(row.si_status), entityLink(row.pi,'Purchase Invoice'), statusBadge(row.pi_status), row.item_code || '--', entityLink(row.batch_no,'Batch'), row.qty ? Number(row.qty).toLocaleString() : '--'];
      }
    );
  }

  function renderAlerts(alerts) {
    if (!alerts || alerts.length === 0) {
      return '<div class="alerts-panel"><div class="alerts-header">No issues found</div></div>';
    }
    var iconMap = { critical: '&#128308;', warning: '&#128992;', info: '&#128993;' };
    var rows = alerts.map(function(a) {
      var actionsHtml = '';
      if (a.action === 'retry') {
        actionsHtml += '<button class="btn-action btn-retry" onclick="handleRetry(\'' + a.entity + '\')">Retry</button>';
      } else if (a.action === 'submit') {
        actionsHtml += '<button class="btn-action btn-submit" onclick="handleSubmit(\'' + a.entity + '\')">Submit</button>';
      }
      if (a.doctype) {
        actionsHtml += '<button class="btn-action" onclick="frappe.set_route(\'Form\', \'' + a.doctype + '\', \'' + a.entity + '\')">Open</button>';
      }
      return '<div class="alert-row"><span class="alert-icon">' + (iconMap[a.severity] || '&#128993;') + '</span><div class="alert-body"><div class="alert-title">' + a.title + '</div><div class="alert-message">' + a.message + '</div></div><div class="alert-actions">' + actionsHtml + '</div></div>';
    }).join('');
    return '<div class="alerts-panel"><div class="alerts-header">Alerts - ' + alerts.length + ' issue' + (alerts.length !== 1 ? 's' : '') + ' found</div><div class="alerts-list">' + rows + '</div></div>';
  }

  function refresh() {
    var fromDate = fromInput.value || null;
    var toDate = toInput.value || null;
    var supplier = supplierInput.value.trim() || null;
    var customer = customerInput.value.trim() || null;

    refreshBtn.disabled = true;
    refreshBtn.textContent = 'Refreshing...';

    frappe.call({ method: 'optimusland.utils.pipeline.get_pipeline_data', args: { from_date: fromDate, to_date: toDate, supplier: supplier, customer: customer } }).then(function(pipelineRes) {
      return frappe.call({ method: 'optimusland.utils.pipeline.get_alerts', args: { from_date: fromDate, to_date: toDate } }).then(function(alertsRes) {
        var data = pipelineRes.message || {};
        var alerts = alertsRes.message || [];
        var html = renderSourcing(data.sourcing || []) + renderManufacturing(data.manufacturing || []) + renderFulfillment(data.fulfillment || []) + renderAlerts(alerts);
        contentEl.innerHTML = html;
        lastRefreshedEl.textContent = 'Last refreshed: ' + new Date().toLocaleString();
        refreshBtn.disabled = false;
        refreshBtn.textContent = 'Refresh';
      });
    }).catch(function() {
      contentEl.innerHTML = '<div class="pipeline-error">Error loading pipeline data</div>';
      refreshBtn.disabled = false;
      refreshBtn.textContent = 'Refresh';
    });
  }

  window.handleRetry = function(prName) {
    frappe.confirm('Retry creating Production Plan for Purchase Receipt ' + prName + '?', function() {
      frappe.call({ method: 'optimusland.utils.pipeline.retry_production_plan', args: { pr_name: prName } }).then(function(r) {
        if (r.message && r.message.success) {
          frappe.show_alert({ message: r.message.message, indicator: 'green' });
          refresh();
        } else {
          frappe.show_alert({ message: r.message ? r.message.message : 'Retry failed', indicator: 'red' });
        }
      });
    });
  };

  window.handleSubmit = function(woName) {
    frappe.confirm('Submit Work Order ' + woName + '?', function() {
      frappe.call({ method: 'optimusland.utils.pipeline.force_submit_work_order', args: { wo_name: woName } }).then(function(r) {
        if (r.message && r.message.success) {
          frappe.show_alert({ message: r.message.message, indicator: 'green' });
          refresh();
        } else {
          frappe.show_alert({ message: r.message ? r.message.message : 'Submit failed', indicator: 'red' });
        }
      });
    });
  };

  autoToggle.addEventListener('change', function() {
    if (this.checked) {
      autoInterval = setInterval(refresh, 300000);
    } else {
      if (autoInterval) clearInterval(autoInterval);
      autoInterval = null;
    }
  });

  refreshBtn.addEventListener('click', refresh);
  supplierInput.addEventListener('change', refresh);
  customerInput.addEventListener('change', refresh);
  fromInput.addEventListener('change', refresh);
  toInput.addEventListener('change', refresh);

  setDefaultDates();
  refresh();
})();
