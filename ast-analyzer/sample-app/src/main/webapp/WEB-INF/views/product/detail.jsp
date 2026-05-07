<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>商品詳細 - ${product.name}</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1>商品詳細</h1>
    <nav>
        <a href="${pageContext.request.contextPath}/product/list">商品一覧に戻る</a>
    </nav>
</div>

<div id="product-detail">
    <h2>${product.name}</h2>
    <table>
        <tr><th>カテゴリ</th><td>${product.category}</td></tr>
        <tr><th>説明</th><td>${product.description}</td></tr>
        <tr><th>価格</th><td>${product.price}円</td></tr>
        <tr><th>在庫</th><td id="stockCount">${product.stock}</td></tr>
    </table>

    <div id="action-buttons">
        <a href="${pageContext.request.contextPath}/product/edit/${product.id}" class="btn-primary">編集</a>
        <form action="${pageContext.request.contextPath}/product/delete/${product.id}" method="post"
              onsubmit="return confirm('削除してよろしいですか？')">
            <button type="submit" class="btn-danger">削除</button>
        </form>
    </div>

    <div id="purchase-area">
        <label for="quantity">数量:</label>
        <input type="number" id="quantity" name="quantity" value="1" min="1" max="${product.stock}">
        <button type="button" id="addCartBtn" onclick="addToCartWithQuantity(${product.id})">カートに追加</button>
        <button type="button" id="buyNowBtn" onclick="buyNow(${product.id})">今すぐ購入</button>
    </div>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
<script src="${pageContext.request.contextPath}/js/product.js"></script>
</body>
</html>
