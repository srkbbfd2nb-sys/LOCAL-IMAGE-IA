"""Client minimal de l'API HTTP de ComfyUI (bibliothèque standard uniquement).

Routes utilisées, vérifiées dans server.py de ComfyUI le 7 octobre 2026 :
/system_stats, /object_info/{classe}, /upload/image, /prompt, /history/{id},
/view, /interrupt.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from local_image_ia.gouvernance import ArretDeclare, Capacite, EtatCapacite


class ClientComfy:
    def __init__(self, url: str = "http://127.0.0.1:8188", delai: float = 30.0):
        self.url = url.rstrip("/")
        self.delai = delai
        self.client_id = str(uuid.uuid4())

    # ----- transport ----------------------------------------------------------------

    def _requete(self, methode: str, chemin: str, corps: bytes | None = None,
                 entetes: dict[str, str] | None = None) -> bytes:
        req = urllib.request.Request(self.url + chemin, data=corps, method=methode,
                                     headers=entetes or {})
        try:
            with urllib.request.urlopen(req, timeout=self.delai) as rep:
                return rep.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise ArretDeclare(
                f"ComfyUI a refusé la requête {methode} {chemin} (HTTP {exc.code}).",
                [_resumer_erreur(detail)],
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ArretDeclare(
                f"ComfyUI ne répond pas à {self.url}.",
                ["Lance demarrer.bat (ou ComfyUI) et attends qu'il ait fini de charger.",
                 f"Détail : {exc}"],
            ) from exc

    def _json(self, methode: str, chemin: str, donnees: dict | None = None) -> dict:
        corps = None if donnees is None else json.dumps(donnees).encode("utf-8")
        entetes = {"Content-Type": "application/json"} if corps is not None else {}
        return json.loads(self._requete(methode, chemin, corps, entetes) or b"{}")

    # ----- sonde --------------------------------------------------------------------

    def joignable(self) -> bool:
        try:
            self._requete("GET", "/system_stats")
            return True
        except ArretDeclare:
            return False

    def attendre_demarrage(self, delai_max: float = 600.0, intervalle: float = 3.0) -> None:
        debut = time.monotonic()
        while not self.joignable():
            if time.monotonic() - debut > delai_max:
                raise ArretDeclare(f"ComfyUI n'a pas démarré en {int(delai_max)} s.")
            time.sleep(intervalle)

    def stats(self) -> dict:
        return self._json("GET", "/system_stats")

    def info_noeud(self, classe: str) -> dict | None:
        d = self._json("GET", "/object_info/" + urllib.parse.quote(classe))
        return d.get(classe)

    def sonder(self, noeuds: tuple[str, ...], modeles: dict[tuple[str, str], str]) -> list[Capacite]:
        """Vérifie nœuds et fichiers de modèles. ``modeles`` : {(classe, entrée): fichier}."""
        capacites: list[Capacite] = []
        stats = self.stats()
        for dev in stats.get("devices", []):
            vram = dev.get("vram_total", 0) / 1024**3
            capacites.append(Capacite(f"GPU : {dev.get('name', '?')}", EtatCapacite.VERIFIE,
                                      "ComfyUI /system_stats", f"{vram:.1f} Go de mémoire vidéo"))
        manquants = [c for c in noeuds if self.info_noeud(c) is None]
        if manquants:
            raise ArretDeclare(
                "Nœuds ComfyUI absents : ComfyUI n'est pas assez récent pour FLUX.2 klein.",
                manquants + ["Mets ComfyUI à jour (update\\update_comfyui.bat dans le dossier portable)."],
            )
        capacites.append(Capacite("Nœuds du workflow FLUX.2 klein", EtatCapacite.VERIFIE,
                                  "ComfyUI /object_info"))
        absents = []
        for (classe, entree), fichier in modeles.items():
            info = self.info_noeud(classe) or {}
            disponibles = _options(info, entree)
            if fichier not in disponibles:
                absents.append(f"{fichier} (attendu par {classe}.{entree})")
        if absents:
            raise ArretDeclare(
                "Fichiers de modèle introuvables dans ComfyUI.",
                absents + ["Relance windows\\installer.ps1, ou place les fichiers dans "
                           "ComfyUI\\models\\ (diffusion_models, text_encoders, vae)."],
            )
        capacites.append(Capacite("Fichiers du modèle", EtatCapacite.VERIFIE, "ComfyUI /object_info",
                                  ", ".join(modeles.values())))
        return capacites

    # ----- exécution ----------------------------------------------------------------

    def televerser(self, chemin: str | Path, nom: str) -> str:
        donnees = Path(chemin).read_bytes()
        limite = "----local-image-ia-" + uuid.uuid4().hex
        parties = [
            _champ(limite, "overwrite", "true"),
            _champ(limite, "type", "input"),
            (f"--{limite}\r\nContent-Disposition: form-data; name=\"image\"; "
             f"filename=\"{nom}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
            + donnees + b"\r\n",
            f"--{limite}--\r\n".encode(),
        ]
        rep = json.loads(self._requete(
            "POST", "/upload/image", b"".join(parties),
            {"Content-Type": f"multipart/form-data; boundary={limite}"},
        ))
        sous = rep.get("subfolder") or ""
        return f"{sous}/{rep['name']}" if sous else rep["name"]

    def soumettre(self, graphe: dict) -> str:
        rep = self._json("POST", "/prompt", {"prompt": graphe, "client_id": self.client_id})
        if rep.get("node_errors"):
            raise ArretDeclare("ComfyUI a refusé le workflow.",
                               [_resumer_erreur(json.dumps(rep["node_errors"]))])
        return rep["prompt_id"]

    def attendre(self, prompt_id: str, delai_max: float, intervalle: float = 1.0) -> dict:
        """Attend la fin d'une génération et renvoie ses sorties."""
        debut = time.monotonic()
        while True:
            hist = self._json("GET", f"/history/{prompt_id}").get(prompt_id)
            if hist:
                statut = hist.get("status", {})
                if statut.get("status_str") == "error":
                    raise ArretDeclare("La génération a échoué dans ComfyUI.",
                                       _messages_erreur(statut.get("messages", [])))
                if statut.get("completed", True) and hist.get("outputs"):
                    return hist["outputs"]
            if time.monotonic() - debut > delai_max:
                self.interrompre()
                raise ArretDeclare(
                    f"Génération interrompue : plus de {int(delai_max)} s.",
                    ["Le budget de temps par photo est dépassé ; augmente-le ou réduis le "
                     "nombre de candidats."],
                )
            time.sleep(intervalle)

    def telecharger(self, info: dict) -> bytes:
        q = urllib.parse.urlencode({"filename": info["filename"],
                                    "subfolder": info.get("subfolder", ""),
                                    "type": info.get("type", "output")})
        return self._requete("GET", "/view?" + q)

    def images_de_sortie(self, sorties: dict) -> list[dict]:
        return [img for noeud in sorties.values() for img in noeud.get("images", [])
                if img.get("type", "output") == "output"]

    def interrompre(self) -> None:
        try:
            self._requete("POST", "/interrupt", b"{}", {"Content-Type": "application/json"})
        except ArretDeclare:
            pass


def _champ(limite: str, nom: str, valeur: str) -> bytes:
    return (f"--{limite}\r\nContent-Disposition: form-data; name=\"{nom}\"\r\n\r\n"
            f"{valeur}\r\n").encode()


def _options(info: dict, entree: str) -> list[str]:
    for groupe in ("required", "optional"):
        spec = info.get("input", {}).get(groupe, {}).get(entree)
        if spec and isinstance(spec[0], list):
            return spec[0]
        if spec and isinstance(spec[0], str) and spec[0] == "COMBO" and len(spec) > 1:
            return spec[1].get("options", [])
    return []


def _messages_erreur(messages: list) -> list[str]:
    sortie = []
    for m in messages:
        if isinstance(m, (list, tuple)) and len(m) == 2 and m[0] == "execution_error":
            d = m[1]
            sortie.append(f"{d.get('node_type', '?')} : {d.get('exception_message', '').strip()}")
            if "out of memory" in d.get("exception_message", "").lower():
                sortie.append("Mémoire insuffisante : ferme les autres applications, ou "
                              "passe au modèle quantifié (voir docs/FEUILLE_DE_ROUTE.md).")
    return sortie or ["Aucun détail fourni par ComfyUI."]


def _resumer_erreur(texte: str, limite: int = 600) -> str:
    texte = " ".join(texte.split())
    return texte if len(texte) <= limite else texte[:limite] + " …"
