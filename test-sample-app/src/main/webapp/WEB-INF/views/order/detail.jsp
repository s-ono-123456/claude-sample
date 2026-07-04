<%@ page contentType="text/html;charset=UTF-8" language="java" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>注文詳細</title>
</head>
<body>
<h1>注文詳細</h1>

<p><a href="${pageContext.request.contextPath}/order/search">← 検索画面に戻る</a></p>

<h2>注文基本情報</h2>
<table border="1" cellpadding="4">
    <tr><th>注文ID</th><td>${result.order.id}</td></tr>
    <tr><th>顧客名</th><td>${result.order.customerName}</td></tr>
    <tr><th>会員ランク</th><td>${result.order.memberRank}</td></tr>
    <tr><th>注文日</th><td>${result.order.orderDate}</td></tr>
    <tr><th>支払方法</th><td>${result.order.paymentMethod}</td></tr>
    <tr><th>クーポンコード</th><td>${empty result.order.couponCode ? '（なし）' : result.order.couponCode}</td></tr>
</table>

<h2>注文明細</h2>
<table border="1" cellpadding="4">
    <tr>
        <th>商品名</th>
        <th>カテゴリ</th>
        <th>単価</th>
        <th>数量</th>
        <th>明細小計</th>
    </tr>
    <c:forEach var="item" items="${result.order.items}">
        <tr>
            <td>${item.productName}</td>
            <td>${item.productCategory}</td>
            <td>${item.unitPrice}</td>
            <td>${item.quantity}</td>
            <td>${item.unitPrice * item.quantity}</td>
        </tr>
    </c:forEach>
</table>

<h2>金額計算結果</h2>
<table border="1" cellpadding="4">
    <tr><th>小計</th><td>${result.subtotal}</td></tr>
    <tr><th>割引合計</th><td>${result.totalDiscount}</td></tr>
    <tr><th>税額</th><td>${result.taxAmount}</td></tr>
    <tr><th>配送料</th><td>${result.shippingFee}</td></tr>
    <tr><th>決済手数料</th><td>${result.paymentFee}</td></tr>
    <tr><th>特典合計</th><td>${result.bonusDiscount}</td></tr>
    <tr><th>合計金額</th><td><b>${result.totalAmount}</b></td></tr>
    <tr><th>獲得ポイント</th><td>${result.earnedPoints}</td></tr>
</table>

</body>
</html>
