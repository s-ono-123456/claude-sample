function completeOrder(orderId) {
    if (!confirm('受け取りを完了としてマークしますか？')) {
        return;
    }
    ajaxPost(contextPath + '/order/api/complete/' + orderId, {}, function(response) {
        if (response.success) {
            showMessage('注文を完了としてマークしました', 'success');
            var statusEl = document.getElementById('orderStatus');
            if (statusEl) statusEl.textContent = 'COMPLETED';
            var completeBtn = document.getElementById('completeBtn');
            if (completeBtn) completeBtn.disabled = true;
        }
    }, function(status) {
        showMessage('ステータス更新に失敗しました (status: ' + status + ')', 'error');
    });
}

function loadOrderDetail(orderId) {
    ajaxGet(contextPath + '/order/api/detail/' + orderId, function(order) {
        renderOrderItems(order.items);
    }, function(status) {
        showMessage('注文詳細の取得に失敗しました', 'error');
    });
}

function renderOrderItems(items) {
    var tbody = document.querySelector('#itemsTable tbody');
    if (!tbody) return;
    tbody.innerHTML = items.map(function(item) {
        return '<tr><td>' + item.productId + '</td><td>' + item.quantity +
               '</td><td>' + item.unitPrice + '円</td><td>' +
               (item.quantity * item.unitPrice) + '円</td></tr>';
    }).join('');
}
