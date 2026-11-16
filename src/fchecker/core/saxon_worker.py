"""Processus fils dédié à SaxonC (seul module qui importe ``saxonche``).

Pourquoi un processus : saxonche garde le verrou global de Python (GIL) pendant la compilation et
l'exécution des XSLT. Dans le processus de l'application, cela gelait l'interface (≈ 1,6 s au
démarrage, mesuré). Isolé ici, Saxon ne peut plus bloquer l'interface ni la faire planter, et tous
ses objets naissent et meurent dans le thread principal de ce processus (pas de problème
« wrong IsolateThread » à la fermeture).

Protocole (``multiprocessing`` Pipe, messages picklés) :
    ("compile", chemin)            → ("ok", None)
    ("transform", chemin, xml)     → ("ok", svrl_str)
    ("stop",)                      → ("ok", None), puis fin du processus
Toute erreur → ("err", "Type: message").
"""
from __future__ import annotations


def serve(conn) -> None:
    from saxonche import PySaxonProcessor

    proc = PySaxonProcessor(license=False)
    xslt = proc.new_xslt30_processor()
    compiled: dict[str, object] = {}

    def compile_(path: str):
        exe = compiled.get(path)
        if exe is None:
            exe = xslt.compile_stylesheet(stylesheet_file=path)
            if exe is None:
                raise RuntimeError(f"compilation impossible : {path}")
            compiled[path] = exe
        return exe

    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):  # processus parent disparu
            break
        op = msg[0]
        try:
            if op == "stop":
                conn.send(("ok", None))
                break
            if op == "compile":
                compile_(msg[1])
                conn.send(("ok", None))
            elif op == "transform":
                exe = compile_(msg[1])
                node = proc.parse_xml(xml_text=msg[2])
                result = exe.transform_to_string(xdm_node=node)
                del node
                if result is None:
                    raise RuntimeError("exécution du schematron sans résultat")
                conn.send(("ok", result))
            else:
                conn.send(("err", f"ValueError: opération inconnue {op!r}"))
        except Exception as exc:  # erreur de règle ou de document : renvoyée, le processus continue
            try:
                conn.send(("err", f"{type(exc).__name__}: {exc}"))
            except OSError:
                break
    compiled.clear()
    del xslt, proc
