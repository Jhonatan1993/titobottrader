#!/usr/bin/env python3
"""Configuración local de Telegram; no escribe el token en archivos locales."""
import json
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

SSH_COMMAND = [
    "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=yes", "root@titobottrader.tech",
    "python3", "-u", "/opt/titobot-monitor/setup_visual_backend.py",
]


class SetupWindow:
    def __init__(self, root):
        self.root = root
        self.process = None
        self.chats = []
        root.title("Alertas TitoBot")
        root.geometry("540x320")
        root.protocol("WM_DELETE_WINDOW", self.close)

        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Configurar alertas de Telegram", font=("Arial", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Pega el token nuevo de BotFather. No lo envíes en el chat.").pack(anchor="w", pady=(12, 4))
        self.token = ttk.Entry(frame, show="•", width=55)
        self.token.pack(fill="x")
        self.revoked = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Confirmo que he revocado el token publicado anteriormente",
            variable=self.revoked,
        ).pack(anchor="w", pady=8)
        self.connect_button = ttk.Button(frame, text="Buscar mi chat", command=self.connect)
        self.connect_button.pack(anchor="w")

        ttk.Label(frame, text="Chat privado:").pack(anchor="w", pady=(12, 4))
        self.chat = ttk.Combobox(frame, state="disabled")
        self.chat.pack(fill="x")
        self.test_button = ttk.Button(frame, text="Enviar mensaje de prueba", command=self.send_test, state="disabled")
        self.test_button.pack(anchor="w", pady=8)
        self.status = ttk.Label(frame, text="Las alertas todavía no están activas.", wraplength=500)
        self.status.pack(anchor="w")

    def connect(self):
        token = self.token.get().strip()
        if not self.revoked.get():
            messagebox.showwarning("Seguridad", "Revoca primero el token publicado en el chat y confirma la casilla.")
            return
        if not token:
            messagebox.showwarning("Token", "Pega el token nuevo de BotFather.")
            return
        self.token.delete(0, "end")
        self.connect_button.configure(state="disabled")
        self.status.configure(text="Conectando y buscando chats privados…")
        threading.Thread(target=self._connect_worker, args=(token,), daemon=True).start()

    def _connect_worker(self, token):
        try:
            process = subprocess.Popen(
                SSH_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            )
            self.process = process
            process.stdin.write(json.dumps({"token": token}) + "\n")
            process.stdin.flush()
            token = None
            line = process.stdout.readline()
            response = json.loads(line) if line else {"error": "No se pudo conectar a la VPS o verificar SSH."}
            self.root.after(0, self._show_chats, response)
        except (OSError, ValueError, BrokenPipeError):
            self.root.after(0, self._show_chats, {"error": "No se pudo conectar a la VPS."})

    def _show_chats(self, response):
        if response.get("error"):
            self.status.configure(text=response["error"])
            self.connect_button.configure(state="normal")
            self._stop_process()
            return
        self.chats = response.get("chats", [])
        if not self.chats:
            self.status.configure(text="No se encontró un chat privado. Envía /start al bot y vuelve a intentarlo.")
            self.connect_button.configure(state="normal")
            self._stop_process()
            return
        self.chat.configure(values=[f'{c["index"] + 1}. {c["name"]}' for c in self.chats], state="readonly")
        self.chat.current(0)
        self.test_button.configure(state="normal")
        self.status.configure(text="Selecciona tu chat y envía el mensaje de prueba.")

    def send_test(self):
        index = self.chat.current()
        if index < 0 or self.process is None:
            return
        if not messagebox.askyesno("Confirmar", "¿Enviar un mensaje de prueba al chat seleccionado?"):
            return
        self.test_button.configure(state="disabled")
        self.status.configure(text="Enviando mensaje de prueba…")
        threading.Thread(target=self._test_worker, args=(self.chats[index]["index"],), daemon=True).start()

    def _test_worker(self, index):
        try:
            self.process.stdin.write(json.dumps({"index": index}) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            response = json.loads(line) if line else {"error": "La configuración no terminó correctamente."}
            self.root.after(0, self._show_result, response)
        except (OSError, ValueError, BrokenPipeError):
            self.root.after(0, self._show_result, {"error": "No se pudo completar la prueba."})

    def _show_result(self, response):
        if response.get("success"):
            self.status.configure(text="Telegram aceptó la prueba. Revisa tu chat; las alertas aún no están activas.")
            messagebox.showinfo("Prueba enviada", "Telegram aceptó el mensaje de prueba. Revisa si llegó a tu chat.")
        else:
            self.status.configure(text=response.get("error", "No se pudo completar la configuración."))
            self.connect_button.configure(state="normal")
        self._stop_process()

    def _stop_process(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            self.process = None

    def close(self):
        self._stop_process()
        self.root.destroy()


if __name__ == "__main__":
    app = tk.Tk()
    SetupWindow(app)
    app.mainloop()
