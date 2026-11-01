"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function element() {
    return {
        value: "", disabled: false, open: false, textContent: "",
        listeners: {},
        addEventListener(name, handler) { this.listeners[name] = handler; },
        replaceChildren(option) { this.value = option.value; },
        add() { },
    };
}

async function main() {
    const elements = Object.fromEntries(
        ["telegram-form", "token", "password", "chat", "manual-chat",
            "manual-chat-options", "result", "discover", "status"].map(id => [id, element()])
    );
    elements.token.value = "test-token";
    elements.password.value = "test-password";
    const requests = [];
    const context = {
        document: {
            getElementById: id => elements[id],
            querySelector: () => ({ content: "test-csrf" }),
        },
        window: { confirm: () => true },
        Option: function (name, value) { this.name = name; this.value = value; },
        fetch: async (url, options) => {
            if (options && options.method === "POST") requests.push(JSON.parse(options.body));
            return { ok: true, json: async () => ({ configured: true, service: "active", message: "ok" }) };
        },
    };
    const source = fs.readFileSync(path.join(__dirname, "../dashboard/static/js/telegram_monitor.js"), "utf8");
    vm.runInNewContext(source, context);
    const chat = elements.chat;
    const manual = elements["manual-chat"];
    const options = elements["manual-chat-options"];
    assert.equal(manual.disabled, true);
    options.open = true;
    options.listeners.toggle();
    assert.equal(manual.disabled, false);
    manual.value = "Hola";
    chat.value = "123";
    chat.listeners.change();
    assert.equal(manual.disabled, true);
    await elements["telegram-form"].listeners.submit({ preventDefault() { } });
    assert.equal(requests[0].chat_id, "123");
    chat.value = "";
    chat.listeners.change();
    assert.equal(manual.disabled, false);
    manual.value = "456";
    await elements["telegram-form"].listeners.submit({ preventDefault() { } });
    assert.equal(requests[1].chat_id, "456");
    options.open = false;
    options.listeners.toggle();
    assert.equal(manual.disabled, true);
    console.log("Prueba de selección de chat e ID manual: correcta");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
