<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>注文詳細</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1>注文詳細</h1>
    <nav>
        <a href="${pageContext.request.contextPath}/order/list">注文履歴に戻る</a>
    </nav>
</div>

<div id="order-detail">
    <h2>注文 #${order.id}</h2>
    <table>
        <tr><th>注文日</th><td>${order.orderDate}</td></tr>
        <tr><th>ステータス</th><td id="orderStatus">${order.status}</td></tr>
        <tr><th>合計金額</th><td>${order.totalAmount}円</td></tr>
    </table>

    <h3>注文商品</h3>
    <table id="itemsTable">
        <thead>
            <tr>
                <th>商品ID</th>
                <th>数量</th>
                <th>単価</th>
                <th>小計</th>
            </tr>
        </thead>
        <tbody>
            <c:forEach var="item" items="${order.items}">
            <tr>
                <td>
                    <a href="${pageContext.request.contextPath}/product/detail/${item.productId}">${item.productId}</a>
                </td>
                <td>${item.quantity}</td>
                <td>${item.unitPrice}円</td>
                <td>${item.quantity * item.unitPrice}円</td>
            </tr>
            </c:forEach>
        </tbody>
    </table>

    <c:if test="${order.status == 'PENDING'}">
        <div id="action-area">
            <button type="button" id="completeBtn"
                    onclick="completeOrder(${order.id})">受け取り完了</button>
        </div>
    </c:if>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
<script src="${pageContext.request.contextPath}/js/order.js"></script>
</body>
</html>
