<%@ page contentType="text/html;charset=UTF-8" language="java" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>注文検索</title>
</head>
<body>
<h1>注文検索</h1>

<form action="${pageContext.request.contextPath}/order/search" method="get">
    <table>
        <tr>
            <td>顧客名（部分一致）</td>
            <td><input type="text" name="customerName" value="${criteria.customerName}"/></td>
        </tr>
        <tr>
            <td>注文日（From）</td>
            <td><input type="date" name="orderDateFrom" value="${criteria.orderDateFrom}"/></td>
        </tr>
        <tr>
            <td>注文日（To）</td>
            <td><input type="date" name="orderDateTo" value="${criteria.orderDateTo}"/></td>
        </tr>
        <tr>
            <td>会員ランク</td>
            <td>
                <select name="memberRank">
                    <option value="" ${empty criteria.memberRank ? 'selected' : ''}>（指定なし）</option>
                    <option value="BRONZE" ${criteria.memberRank == 'BRONZE' ? 'selected' : ''}>BRONZE</option>
                    <option value="SILVER" ${criteria.memberRank == 'SILVER' ? 'selected' : ''}>SILVER</option>
                    <option value="GOLD" ${criteria.memberRank == 'GOLD' ? 'selected' : ''}>GOLD</option>
                    <option value="PLATINUM" ${criteria.memberRank == 'PLATINUM' ? 'selected' : ''}>PLATINUM</option>
                </select>
            </td>
        </tr>
    </table>
    <button type="submit">検索</button>
</form>

<h2>検索結果</h2>

<c:if test="${empty orders}">
    <p>該当する注文がありません。</p>
</c:if>

<c:if test="${not empty orders}">
    <table border="1" cellpadding="4">
        <tr>
            <th>注文ID</th>
            <th>顧客名</th>
            <th>会員ランク</th>
            <th>注文日</th>
            <th>支払方法</th>
        </tr>
        <c:forEach var="order" items="${orders}">
            <tr>
                <td><a href="${pageContext.request.contextPath}/order/detail/${order.id}">${order.id}</a></td>
                <td>${order.customerName}</td>
                <td>${order.memberRank}</td>
                <td>${order.orderDate}</td>
                <td>${order.paymentMethod}</td>
            </tr>
        </c:forEach>
    </table>
</c:if>

</body>
</html>
