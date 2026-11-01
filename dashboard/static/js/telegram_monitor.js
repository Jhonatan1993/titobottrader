"use strict";

const form = document.getElementById("telegram-form");
const token = document.getElementById("token");
const password = document.getElementById("password");
const chat = document.getElementById("chat");
const manual = document.getElementById("manual-chat");
const manualOptions = document.getElementById("manual-chat-options");
const result = document.getElementById("result");
const csrf = document.querySelector('meta[name="csrf-token"]').content;

async function post(path, body) {
    const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "No se pudo completar la solicitud.");
    return data;
}

async function loadStatus() {
    try {
        const response = await fetch("/api/admin/telegram-monitor/status", { credentials: "same-origin" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Estado no disponible.");
        document.getElementById("status").textContent =
            `Configuración: ${data.configured ? "guardada" : "ausente"}. Servicio: ${data.service}.`;
    } catch (error) {
        document.getElementById("status").textContent = "No se pudo consultar el estado del monitor.";
    }
}

function updateManualInput() {
    manual.disabled = !manualOptions.open || Boolean(chat.value);
}

manualOptions.addEventListener("toggle", updateManualInput);
chat.addEventListener("change", updateManualInput);
updateManualInput();

document.getElementById("discover").addEventListener("click", async () => {
    result.textContent = "Buscando chats privados…";
    try {
        const data = await post("/api/admin/telegram-monitor/discover", {
            token: token.value.trim(), password: password.value,
        });
        chat.replaceChildren(new Option("Selecciona un chat", ""));
        for (const item of data.chats) chat.add(new Option(item.name, item.id));
        updateManualInput();
        result.textContent = data.chats.length
            ? `Bot @${data.bot}: selecciona tu chat.`
            : `Bot @${data.bot}: no hay mensajes privados pendientes. Envía un mensaje al bot e intenta de nuevo.`;
    } catch (error) {
        result.textContent = error.message;
    }
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const chatId = chat.value || (!manual.disabled ? manual.value.trim() : "");
    if (!chatId) {
        result.textContent = "Selecciona un chat privado o introduce su ID.";
        return;
    }
    if (!window.confirm("Se enviará una prueba y se reiniciará solo el monitor de Telegram. ¿Continuar?")) return;
    result.textContent = "Enviando prueba y configurando el monitor…";
    try {
        const data = await post("/api/admin/telegram-monitor/configure", {
            token: token.value.trim(), password: password.value, chat_id: chatId,
        });
        token.value = "";
        password.value = "";
        result.textContent = data.message;
        await loadStatus();
    } catch (error) {
        result.textContent = error.message;
    }
});

loadStatus();
