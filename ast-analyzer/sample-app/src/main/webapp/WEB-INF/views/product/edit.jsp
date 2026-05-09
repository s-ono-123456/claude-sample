<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title><c:choose><c:when test="${product.id != null}">商品編集</c:when><c:otherwise>新規商品登録</c:otherwise></c:choose></title>
    <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css">
</head>
<body>
<div id="header">
    <h1><c:choose><c:when test="${product.id != null}">商品編集</c:when><c:otherwise>新規商品登録</c:otherwise></c:choose></h1>
</div>

<div id="edit-form">
    <c:choose>
        <c:when test="${product.id != null}">
            <form action="${pageContext.request.contextPath}/product/update" method="post" id="productForm">
                <input type="hidden" name="id" value="${product.id}">
        </c:when>
        <c:otherwise>
            <form action="${pageContext.request.contextPath}/product/create" method="post" id="productForm">
        </c:otherwise>
    </c:choose>

        <div class="form-group">
            <label for="name">商品名:</label>
            <input type="text" id="name" name="name" value="${product.name}" required>
        </div>

        <div class="form-group">
            <label for="description">説明:</label>
            <textarea id="description" name="description">${product.description}</textarea>
        </div>

        <div class="form-group">
            <label for="price">価格:</label>
            <input type="number" id="price" name="price" value="${product.price}" required min="0">
        </div>

        <div class="form-group">
            <label for="stock">在庫数:</label>
            <input type="number" id="stock" name="stock" value="${product.stock}" required min="0">
        </div>

        <div class="form-group">
            <label for="category">カテゴリ:</label>
            <select id="category" name="category">
                <option value="electronics" <c:if test="${product.category == 'electronics'}">selected</c:if>>電子機器</option>
                <option value="clothing" <c:if test="${product.category == 'clothing'}">selected</c:if>>衣類</option>
                <option value="food" <c:if test="${product.category == 'food'}">selected</c:if>>食品</option>
            </select>
        </div>

        <div class="form-actions">
            <button type="submit" id="saveBtn" onclick="validateForm()">保存</button>
            <a href="${pageContext.request.contextPath}/product/list">キャンセル</a>
        </div>
    </form>
</div>

<script src="${pageContext.request.contextPath}/js/common.js"></script>
<script src="${pageContext.request.contextPath}/js/product.js"></script>
</body>
</html>
