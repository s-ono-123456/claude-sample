<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>商品一覧</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1>商品一覧</h1>
    <nav>
        <a href="${pageContext.request.contextPath}/user/mypage">マイページ</a>
        <a href="${pageContext.request.contextPath}/order/list">注文履歴</a>
        <a href="${pageContext.request.contextPath}/user/logout">ログアウト</a>
    </nav>
</div>

<div id="search-area">
    <form action="${pageContext.request.contextPath}/product/list" method="get">
        <select name="category" id="categorySelect">
            <option value="">すべてのカテゴリ</option>
            <option value="electronics" <c:if test="${category == 'electronics'}">selected</c:if>>電子機器</option>
            <option value="clothing" <c:if test="${category == 'clothing'}">selected</c:if>>衣類</option>
            <option value="food" <c:if test="${category == 'food'}">selected</c:if>>食品</option>
        </select>
        <button type="submit" id="searchBtn">検索</button>
    </form>
</div>

<div id="product-list">
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>商品名</th>
                <th>カテゴリ</th>
                <th>価格</th>
                <th>在庫</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            <c:forEach var="product" items="${products}">
            <tr>
                <td>${product.id}</td>
                <td>
                    <a href="${pageContext.request.contextPath}/product/detail/${product.id}">${product.name}</a>
                </td>
                <td>${product.category}</td>
                <td>${product.price}円</td>
                <td>${product.stock}</td>
                <td>
                    <a href="${pageContext.request.contextPath}/product/edit/${product.id}" class="btn-edit">編集</a>
                    <button type="button" class="btn-delete" onclick="deleteProduct(${product.id})">削除</button>
                    <button type="button" class="btn-cart" onclick="addToCart(${product.id})">カートに追加</button>
                </td>
            </tr>
            </c:forEach>
        </tbody>
    </table>
</div>

<div id="action-area">
    <a href="${pageContext.request.contextPath}/product/new" class="btn-primary">新規商品登録</a>
    <button type="button" id="placeOrderBtn" onclick="placeOrder()">注文する</button>
</div>

<div id="cart-panel" style="display:none">
    <h2>カート</h2>
    <div id="cart-items"></div>
    <div id="cart-total"></div>
    <button type="button" onclick="checkout()">チェックアウト</button>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
<script src="${pageContext.request.contextPath}/js/product.js"></script>
</body>
</html>
