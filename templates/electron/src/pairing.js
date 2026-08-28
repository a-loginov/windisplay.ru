const codeEl = document.getElementById("code");
const waitingRow = document.getElementById("waitingRow");
const errorBox = document.getElementById("errorBox");
const errorText = document.getElementById("errorText");
const retryBtn = document.getElementById("retryBtn");

let pollTimer = null;

function showError(message) {
    codeEl.textContent = "— — — —";
    codeEl.classList.add("code--placeholder");
    waitingRow.style.display = "none";
    errorBox.style.display = "block";
    errorText.textContent = message;
}

function showWaiting() {
    errorBox.style.display = "none";
    waitingRow.style.display = "flex";
}

async function begin() {
    showWaiting();
    codeEl.classList.add("code--placeholder");
    codeEl.textContent = "Получаем код…";

    try {
        const { code } = await window.api.startPairing();
        codeEl.textContent = code;
        codeEl.classList.remove("code--placeholder");
        pollTimer = setInterval(poll, 3000);
    } catch (err) {
        showError("Не удалось связаться с сервером. Проверьте интернет-соединение.");
    }
}

async function poll() {
    try {
        const { paired } = await window.api.pollPairing();
        if (paired) {
            clearInterval(pollTimer);
            waitingRow.querySelector("span:last-child").textContent = "Подключено! Запускаем экран…";
            setTimeout(() => {
                window.location.href = "player.html";
            }, 900);
        }
    } catch {
        // transient network error while waiting — keep polling silently
    }
}

retryBtn.addEventListener("click", begin);

begin();
