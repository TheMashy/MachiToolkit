"""La bulle de Claude Code, pour les sessions dans le cloud.

« Une bulle de statut quand Claude reflechit : rouge quand quelque chose est
bloque et attend une confirmation, jaune quand il travaille, vert quand c'est
fini. » Une session dans le cloud ne joint pas le PC : chaque crochet de Claude
Code (voir .claude/settings.json) lance ce script, qui pose l'etape de la
session chez BrainDebugger ; Machi Tool vient l'y relever et l'affiche en bulle
sur le panneau LED.

Ce qui part : le nom de l'etape, la session, l'outil, le type de notification
(et son court message), le nom du dossier -- ni la demande, ni ce que Claude
lit ou ecrit. Sans la variable MACHITOOL_BULLE_CLE (la page Panneau LED de
Machi Tool la donne) -- ou, pour une session ouverte avant qu'on l'ajoute a
l'environnement (elle ne la recoit jamais), le fichier .claude/bulle_cle.local
a cote de ce script, jamais commite --, il ne fait rien. Il ne gene jamais Claude Code : trois
secondes au plus, il ne dit rien, il rend toujours 0.
"""
import json
import os
import sys
import urllib.request

URL = os.environ.get("MACHITOOL_BULLE_URL",
                     "https://braindebugger-production.up.railway.app/api/machitool/claude")


def a_envoyer(e):
    """Ce qui part de cet evenement, ou None : une notification qui n'attend
    rien de toi (« Claude attend ta prochaine demande ») effacerait le vert."""
    nom = str(e.get("hook_event_name") or "")
    corps = {"hook_event_name": nom, "session_id": str(e.get("session_id") or "")[:80],
             "dossier": os.path.basename(str(e.get("cwd") or "").rstrip("/\\"))[:40]}
    if nom == "Notification":
        genre = str(e.get("notification_type") or "")
        message = str(e.get("message") or "")[:120]
        bloque = genre in ("permission_prompt", "elicitation_dialog") or (not genre and "permission" in message.lower())
        if not bloque:
            return None
        corps.update(notification_type=genre, message=message)
    elif nom in ("PreToolUse", "PostToolUse"):
        corps["tool_name"] = str(e.get("tool_name") or "")[:60]
    elif nom not in ("UserPromptSubmit", "Stop", "SessionEnd"):
        return None
    return corps


def cle_de_l_environnement():
    """La variable MACHITOOL_BULLE_CLE -- meme collee avec une marque
    d'encodage invisible (\ufeff) ou des espaces, dans son nom ou sa valeur.
    Sinon, le fichier bulle_cle.local (MACHITOOL_BULLE_FICHIER pour les tests)."""
    for nom, valeur in os.environ.items():
        if nom.strip().lstrip("\ufeff") == "MACHITOOL_BULLE_CLE":
            return valeur.strip().lstrip("\ufeff").strip()
    fichier = os.environ.get("MACHITOOL_BULLE_FICHIER") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                         "bulle_cle.local")
    try:
        with open(fichier, encoding="utf-8-sig") as f:
            texte = f.read().strip()
    except OSError:
        return ""
    return texte.split("=", 1)[-1].strip()           # la cle seule, ou la ligne « MACHITOOL_BULLE_CLE=... »


def main():
    cle = cle_de_l_environnement()
    if not cle:
        return
    try:
        corps = a_envoyer(json.load(sys.stdin))
    except Exception:
        return
    if corps is None:
        return
    requete = urllib.request.Request(URL, data=json.dumps(corps).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "X-Machitool-Bulle": cle, "User-Agent": "MachiToolkit-bulle"})
    try:
        urllib.request.urlopen(requete, timeout=3).close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
