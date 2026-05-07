var cart = [];

function addToCart(productId) {
    ajaxGet(contextPath + '/product/api/detail/' + productId, function(product) {
        var existing = cart.find(function(item) { return item.productId === productId; });
        if (existing) {
            existing.quantity += 1;
        } else {
            cart.push({
                productId: product.id,
                productName: product.name,
                unitPrice: product.price,
                quantity: 1
            });
        }
        updateCartDisplay();
        showMessage(product.name + ' をカートに追加しました', 'success');
    }, function(status) {
        showMessage('商品情報の取得に失敗しました (status: ' + status + ')', 'error');
    });
}

function addToCartWithQuantity(productId) {
    var quantity = parseInt(document.getElementById('quantity').value);
    if (isNaN(quantity) || quantity < 1) {
        showMessage('数量を正しく入力してください', 'error');
        return;
    }
    ajaxGet(contextPath + '/product/api/detail/' + productId, function(product) {
        var existing = cart.find(function(item) { return item.productId === productId; });
        if (existing) {
            existing.quantity += quantity;
        } else {
            cart.push({
                productId: product.id,
                productName: product.name,
                unitPrice: product.price,
                quantity: quantity
            });
        }
        updateCartDisplay();
        showMessage(product.name + ' x' + quantity + ' をカートに追加しました', 'success');
    }, function(status) {
        showMessage('商品情報の取得に失敗しました', 'error');
    });
}

function buyNow(productId) {
    var quantity = parseInt(document.getElementById('quantity').value);
    ajaxGet(contextPath + '/product/api/detail/' + productId, function(product) {
        var order = {
            items: [{
                productId: product.id,
                quantity: quantity,
                unitPrice: product.price
            }],
            totalAmount: product.price * quantity
        };
        ajaxPost(contextPath + '/order/place', order, function(response) {
            if (response.success) {
                showMessage('注文が完了しました', 'success');
                window.location.href = contextPath + '/order/detail/' + response.orderId;
            } else {
                showMessage(response.error, 'error');
            }
        }, function(status, responseText) {
            var err = JSON.parse(responseText);
            showMessage(err.error || '注文に失敗しました', 'error');
        });
    });
}

function deleteProduct(productId) {
    if (!confirm('この商品を削除してよろしいですか？')) {
        return;
    }
    var form = document.createElement('form');
    form.method = 'post';
    form.action = contextPath + '/product/delete/' + productId;
    document.body.appendChild(form);
    form.submit();
}

function placeOrder() {
    if (cart.length === 0) {
        showMessage('カートに商品がありません', 'error');
        return;
    }
    var totalAmount = cart.reduce(function(sum, item) {
        return sum + item.unitPrice * item.quantity;
    }, 0);
    var order = {
        items: cart.map(function(item) {
            return {
                productId: item.productId,
                quantity: item.quantity,
                unitPrice: item.unitPrice
            };
        }),
        totalAmount: totalAmount
    };
    ajaxPost(contextPath + '/order/place', order, function(response) {
        if (response.success) {
            cart = [];
            updateCartDisplay();
            showMessage('注文が完了しました', 'success');
            setTimeout(function() {
                window.location.href = contextPath + '/order/detail/' + response.orderId;
            }, 1500);
        } else {
            showMessage(response.error, 'error');
        }
    }, function(status, responseText) {
        if (status === 401) {
            window.location.href = contextPath + '/user/login';
        } else {
            var err = JSON.parse(responseText);
            showMessage(err.error || '注文に失敗しました', 'error');
        }
    });
}

function checkout() {
    placeOrder();
}

function updateCartDisplay() {
    var panel = document.getElementById('cart-panel');
    var itemsDiv = document.getElementById('cart-items');
    var totalDiv = document.getElementById('cart-total');
    if (!panel) return;

    if (cart.length === 0) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'block';
    itemsDiv.innerHTML = cart.map(function(item) {
        return '<div>' + item.productName + ' x' + item.quantity + ' = ' + (item.unitPrice * item.quantity) + '円</div>';
    }).join('');
    var total = cart.reduce(function(s, i) { return s + i.unitPrice * i.quantity; }, 0);
    totalDiv.textContent = '合計: ' + total + '円';
}

function validateForm() {
    return validateRequired('productForm');
}

function loadProductsByCategory(category) {
    var url = contextPath + '/product/api/list' + (category ? '?category=' + category : '');
    ajaxGet(url, function(products) {
        renderProductTable(products);
    }, function(status) {
        showMessage('商品一覧の取得に失敗しました', 'error');
    });
}

function renderProductTable(products) {
    var tbody = document.querySelector('#product-list tbody');
    if (!tbody) return;
    tbody.innerHTML = products.map(function(p) {
        return '<tr><td>' + p.id + '</td><td>' + p.name + '</td><td>' + p.category +
               '</td><td>' + p.price + '円</td><td>' + p.stock + '</td><td>' +
               '<button onclick="addToCart(' + p.id + ')">カートに追加</button></td></tr>';
    }).join('');
}

document.addEventListener('DOMContentLoaded', function() {
    var categorySelect = document.getElementById('categorySelect');
    if (categorySelect) {
        categorySelect.addEventListener('change', function() {
            loadProductsByCategory(this.value);
        });
    }
});
