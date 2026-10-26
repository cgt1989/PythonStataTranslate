"""Interfaz del Traductor Stata <-> Python / Stata <-> Python Translator GUI (tkinter)."""
import os
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from traductor import python_to_stata, stata_to_python

REPO = "https://github.com/cgt1989/PythonStataTranslate"
MODOS = {"s2p": (".py", stata_to_python), "p2s": (".do", python_to_stata)}
IDIOMAS = {"Español": "es", "English": "en"}
UI = {
    "es": dict(title="Traductor Stata ⇄ Python", s2p="Stata → Python", p2s="Python → Stata", open="Abrir archivo…",
               translate="Traducir", save="Guardar…", copy="Copiar salida", lang="Idioma:",
               in_s2p="Entrada: do-file (.do)", in_p2s="Entrada: script de Python (.py)",
               out_s2p="Salida: script de Python (.py)", out_p2s="Salida: do-file de Stata (.do)",
               warns="Advertencias", none="Sin advertencias.", saved="Guardado", kinds="Do-file o script", all="Todos",
               file="Archivo", repo="Descarga y código fuente:", err="Error inesperado"),
    "en": dict(title="Stata ⇄ Python Translator", s2p="Stata → Python", p2s="Python → Stata", open="Open file…",
               translate="Translate", save="Save…", copy="Copy output", lang="Language:",
               in_s2p="Input: do-file (.do)", in_p2s="Input: Python script (.py)",
               out_s2p="Output: Python script (.py)", out_p2s="Output: Stata do-file (.do)",
               warns="Warnings", none="No warnings.", saved="Saved", kinds="Do-file or script", all="All",
               file="File", repo="Download and source code:", err="Unexpected error"),
}


def leer(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass


def main():
    root = tk.Tk()
    root.geometry("1150x740")
    lang, modo, ruta = tk.StringVar(value="es"), tk.StringVar(value="s2p"), [None]
    T = lambda k: UI[lang.get()][k]

    def textos(*_):
        root.title(T("title"))
        for k, w in radios.items():
            w.config(text=T(k))
        for k, w in botones.items():
            w.config(text=T(k))
        llang.config(text=T("lang"))
        lin.config(text=T("in_" + modo.get()))
        lout.config(text=T("out_" + modo.get()))
        lav.config(text=f"{T('warns')} ({nav[0]})")
        lrepo.config(text=T("repo"))

    def abrir():
        p = filedialog.askopenfilename(filetypes=[(T("kinds"), "*.do *.ado *.py"), (T("all"), "*.*")])
        if not p:
            return
        ruta[0] = p
        modo.set("p2s" if p.lower().endswith(".py") else "s2p")
        entrada.delete("1.0", "end")
        entrada.insert("1.0", leer(p))
        textos()
        traducir()

    def traducir():
        fn = MODOS[modo.get()][1]
        try:
            codigo, avisos = fn(entrada.get("1.0", "end"), lang.get())
        except Exception as e:  # el motor no deberia fallar, pero la app no debe cerrarse
            codigo, avisos = "", [f"{T('err')}: {e}"]
        salida.delete("1.0", "end")
        salida.insert("1.0", codigo)
        nav[0] = len(avisos)
        textos()
        av.config(state="normal")
        av.delete("1.0", "end")
        av.insert("1.0", "\n".join("⚠ " + a for a in avisos) or T("none"))
        av.config(state="disabled")

    def cambiar_idioma(_=None):
        lang.set(IDIOMAS[combo.get()])
        textos()
        if salida.get("1.0", "end").strip():
            traducir()

    def guardar():
        ext = MODOS[modo.get()][0]
        ini = os.path.splitext(os.path.basename(ruta[0]))[0] if ruta[0] else "traduccion"
        p = filedialog.asksaveasfilename(defaultextension=ext, initialfile=ini + ext,
                                         filetypes=[(T("file"), "*" + ext), (T("all"), "*.*")])
        if p:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(salida.get("1.0", "end").rstrip() + "\n")
            messagebox.showinfo(T("saved"), p)

    def copiar():
        root.clipboard_clear()
        root.clipboard_append(salida.get("1.0", "end"))

    barra = ttk.Frame(root)
    barra.pack(fill="x", padx=8, pady=6)
    radios = {k: ttk.Radiobutton(barra, value=k, variable=modo, command=textos) for k in MODOS}
    for w in radios.values():
        w.pack(side="left", padx=4)
    botones = {k: ttk.Button(barra, command=c) for k, c in
               (("open", abrir), ("translate", traducir), ("save", guardar), ("copy", copiar))}
    for w in botones.values():
        w.pack(side="left", padx=4)
    combo = ttk.Combobox(barra, values=list(IDIOMAS), state="readonly", width=9)
    combo.set("Español")
    combo.bind("<<ComboboxSelected>>", cambiar_idioma)
    combo.pack(side="right")
    llang = ttk.Label(barra)
    llang.pack(side="right", padx=4)

    paneles = ttk.PanedWindow(root, orient="horizontal")
    paneles.pack(fill="both", expand=True, padx=8)
    izq, der = ttk.Frame(paneles), ttk.Frame(paneles)
    paneles.add(izq, weight=1)
    paneles.add(der, weight=1)
    lin, lout = ttk.Label(izq), ttk.Label(der)
    lin.pack(anchor="w")
    lout.pack(anchor="w")
    entrada = ScrolledText(izq, font=("Consolas", 10), undo=True, wrap="none")
    salida = ScrolledText(der, font=("Consolas", 10), undo=True, wrap="none")
    entrada.pack(fill="both", expand=True)
    salida.pack(fill="both", expand=True)

    pie = ttk.Frame(root)
    pie.pack(fill="x", padx=8, pady=(6, 0))
    nav = [0]
    lav = ttk.Label(pie)
    lav.pack(side="left")
    link = tk.Label(pie, text=REPO, fg="#0b5fd6", cursor="hand2", font=("Segoe UI", 9, "underline"))
    link.pack(side="right")
    link.bind("<Button-1>", lambda _: webbrowser.open(REPO))
    lrepo = ttk.Label(pie)
    lrepo.pack(side="right", padx=4)
    av = ScrolledText(root, height=8, font=("Consolas", 10), state="disabled", wrap="word")
    av.pack(fill="x", padx=8, pady=(0, 8))
    textos()
    root.mainloop()


if __name__ == "__main__":
    main()
