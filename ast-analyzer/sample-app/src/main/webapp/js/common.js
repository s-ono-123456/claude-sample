var contextPath = document.querySelector('meta[name="context-path"]')
    ? document.querySelector('meta[name="context-path"]').getAttribute('content')
    : '';

function ajaxGet(url, successCallback, errorCallback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                var data = JSON.parse(xhr.responseText);
                successCallback(data);
            } else {
                if (errorCallback) errorCallback(xhr.status, xhr.responseText);
            }
        }
    };
    xhr.send();
}

function ajaxPost(url, data, successCallback, errorCallback) {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                var responseData = JSON.parse(xhr.responseText);
                successCallback(responseData);
            } else {
                if (errorCallback) errorCallback(xhr.status, xhr.responseText);
            }
        }
    };
    xhr.send(JSON.stringify(data));
}

function showMessage(message, type) {
    var msgDiv = document.getElementById('message-area');
    if (!msgDiv) {
        msgDiv = document.createElement('div');
        msgDiv.id = 'message-area';
        document.body.insertBefore(msgDiv, document.body.firstChild);
    }
    msgDiv.className = type || 'info';
    msgDiv.textContent = message;
    setTimeout(function() { msgDiv.textContent = ''; }, 3000);
}

function validateRequired(formId) {
    var form = document.getElementById(formId);
    var inputs = form.querySelectorAll('[required]');
    for (var i = 0; i < inputs.length; i++) {
        if (!inputs[i].value.trim()) {
            showMessage(inputs[i].previousElementSibling.textContent + 'は必須です', 'error');
            inputs[i].focus();
            return false;
        }
    }
    return true;
}
