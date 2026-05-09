<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>マイページ</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1>マイページ</h1>
    <nav>
        <a href="${pageContext.request.contextPath}/product/list">商品一覧</a>
        <a href="${pageContext.request.contextPath}/order/list">注文履歴</a>
        <a href="${pageContext.request.contextPath}/user/logout">ログアウト</a>
    </nav>
</div>

<div id="user-info">
    <h2>ユーザー情報</h2>
    <form action="${pageContext.request.contextPath}/user/update" method="post" id="userForm">
        <input type="hidden" name="id" value="${user.id}">
        <div class="form-group">
            <label>ユーザー名:</label>
            <span>${user.username}</span>
        </div>
        <div class="form-group">
            <label for="email">メールアドレス:</label>
            <input type="email" id="email" name="email" value="${user.email}">
        </div>
        <div class="form-actions">
            <button type="submit" id="updateBtn">更新</button>
        </div>
    </form>
</div>

<div id="quick-links">
    <h2>クイックリンク</h2>
    <ul>
        <li><a href="${pageContext.request.contextPath}/order/list">注文履歴を確認する</a></li>
        <li><a href="${pageContext.request.contextPath}/product/list">商品を探す</a></li>
    </ul>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
</body>
</html>
