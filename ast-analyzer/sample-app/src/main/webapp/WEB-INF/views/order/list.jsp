<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>注文履歴</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1>注文履歴</h1>
    <nav>
        <a href="${pageContext.request.contextPath}/product/list">商品一覧</a>
        <a href="${pageContext.request.contextPath}/user/mypage">マイページ</a>
    </nav>
</div>

<div id="order-list">
    <c:choose>
        <c:when test="${empty orders}">
            <p>注文履歴はありません。</p>
            <a href="${pageContext.request.contextPath}/product/list">商品を購入する</a>
        </c:when>
        <c:otherwise>
            <table>
                <thead>
                    <tr>
                        <th>注文ID</th>
                        <th>注文日</th>
                        <th>合計金額</th>
                        <th>ステータス</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    <c:forEach var="order" items="${orders}">
                    <tr>
                        <td>${order.id}</td>
                        <td>${order.orderDate}</td>
                        <td>${order.totalAmount}円</td>
                        <td>${order.status}</td>
                        <td>
                            <a href="${pageContext.request.contextPath}/order/detail/${order.id}">詳細</a>
                            <c:if test="${order.status == 'PENDING'}">
                                <form action="${pageContext.request.contextPath}/order/cancel/${order.id}"
                                      method="post" style="display:inline"
                                      onsubmit="return confirm('注文をキャンセルしますか？')">
                                    <button type="submit" class="btn-danger">キャンセル</button>
                                </form>
                            </c:if>
                        </td>
                    </tr>
                    </c:forEach>
                </tbody>
            </table>
        </c:otherwise>
    </c:choose>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
<script src="${pageContext.request.contextPath}/js/order.js"></script>
</body>
</html>
