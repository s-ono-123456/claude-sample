<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>新規ユーザー登録</title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="register-container">
    <h1>新規ユーザー登録</h1>

    <form action="${pageContext.request.contextPath}/user/register" method="post" id="registerForm">
        <div class="form-group">
            <label for="username">ユーザー名:</label>
            <input type="text" id="username" name="username" required>
        </div>
        <div class="form-group">
            <label for="email">メールアドレス:</label>
            <input type="email" id="email" name="email" required>
        </div>
        <div class="form-actions">
            <button type="submit" id="registerBtn" onclick="validateRegisterForm()">登録</button>
            <a href="${pageContext.request.contextPath}/user/login">ログインページへ戻る</a>
        </div>
    </form>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
</body>
</html>
