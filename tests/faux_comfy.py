"""Faux serveur ComfyUI pour les tests : mêmes routes, mêmes formats de réponse.

Le « modèle » simulé : réduit l'image comme ImageScaleToTotalPixels (1 Mpx,
multiples de 16), éclaircit un rectangle central (la modification voulue), applique
une légère dérive de couleur à toute l'image et l'adoucit (comme un vrai modèle).
"""

from __future__ import annotations

import io
import json
import math
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image, ImageFilter

from local_image_ia.workflows import NOEUDS_REQUIS, PRESETS

MODELE = PRESETS["klein4b"]


class FauxComfy:
    def __init__(self, erreur_generation: str | None = None):
        self.entrees: dict[str, bytes] = {}
        self.sorties: dict[str, bytes] = {}
        self.historique: dict[str, dict] = {}
        self.graphes: list[dict] = []
        self.erreur_generation = erreur_generation
        etat = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, code: int, donnees) -> None:
                corps = json.dumps(donnees).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/system_stats":
                    return self._json(200, {"devices": [{"name": "cuda:0 NVIDIA GeForce RTX 3060 Laptop GPU",
                                                         "vram_total": 6 * 1024**3}]})
                if url.path.startswith("/object_info/"):
                    classe = url.path.split("/")[-1]
                    if classe not in NOEUDS_REQUIS:
                        return self._json(200, {})
                    entrees = {}
                    if classe == "UNETLoader":
                        entrees = {"unet_name": [[MODELE.unet], {}]}
                    elif classe == "CLIPLoader":
                        entrees = {"clip_name": [[MODELE.clip], {}]}
                    elif classe == "VAELoader":
                        entrees = {"vae_name": [[MODELE.vae], {}]}
                    return self._json(200, {classe: {"input": {"required": entrees}}})
                if url.path.startswith("/history/"):
                    pid = url.path.split("/")[-1]
                    return self._json(200, {pid: etat.historique[pid]} if pid in etat.historique else {})
                if url.path == "/view":
                    nom = parse_qs(url.query)["filename"][0]
                    corps = etat.sorties[nom]
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(corps)))
                    self.end_headers()
                    self.wfile.write(corps)
                    return None
                return self._json(404, {})

            def do_POST(self):
                longueur = int(self.headers.get("Content-Length", 0))
                corps = self.rfile.read(longueur)
                url = urlparse(self.path)
                if url.path == "/upload/image":
                    limite = self.headers["Content-Type"].split("boundary=")[1].encode()
                    for partie in corps.split(b"--" + limite):
                        if b'name="image"' in partie:
                            entete, _, donnees = partie.partition(b"\r\n\r\n")
                            nom = entete.split(b'filename="')[1].split(b'"')[0].decode()
                            etat.entrees[nom] = donnees[:-2]
                            return self._json(200, {"name": nom, "subfolder": "", "type": "input"})
                    return self._json(400, {})
                if url.path == "/prompt":
                    graphe = json.loads(corps)["prompt"]
                    etat.graphes.append(graphe)
                    inconnus = [n["class_type"] for n in graphe.values()
                                if n["class_type"] not in NOEUDS_REQUIS]
                    if inconnus:
                        return self._json(400, {"error": "x", "node_errors": {"?": inconnus}})
                    pid = str(uuid.uuid4())
                    if etat.erreur_generation:
                        etat.historique[pid] = {"outputs": {}, "status": {
                            "status_str": "error", "completed": False,
                            "messages": [["execution_error", {"node_type": "SamplerCustomAdvanced",
                                                              "exception_message": etat.erreur_generation}]]}}
                    else:
                        nom = f"sortie_{len(etat.sorties)}.png"
                        etat.sorties[nom] = etat._generer(graphe)
                        etat.historique[pid] = {"outputs": {"enregistrement": {"images": [
                            {"filename": nom, "subfolder": "", "type": "output"}]}},
                            "status": {"status_str": "success", "completed": True, "messages": []}}
                    return self._json(200, {"prompt_id": pid, "number": 1, "node_errors": {}})
                if url.path == "/interrupt":
                    return self._json(200, {})
                return self._json(404, {})

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.url = f"http://127.0.0.1:{self.serveur.server_address[1]}"
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def _generer(self, graphe: dict) -> bytes:
        charges = [n for k, n in graphe.items() if n["class_type"] == "LoadImage"]
        if charges:
            premiere = graphe["image_0"]["inputs"]["image"]
            im = Image.open(io.BytesIO(self.entrees[premiere])).convert("RGB")
            w, h = im.size
            f = math.sqrt(1024 * 1024 / (w * h))
            im = im.resize((round(w * f / 16) * 16, round(h * f / 16) * 16), Image.Resampling.BOX)
            a = np.asarray(im).astype(np.float32)
            H, W = a.shape[:2]
            a[int(H * .35):int(H * .65), int(W * .35):int(W * .65)] += 40   # la modification voulue
            a = a * 1.03 + 2                                                  # dérive globale
            im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        else:
            n = graphe["latent"]["inputs"]
            yy, xx = np.mgrid[0:n["height"], 0:n["width"]]
            a = np.stack([xx % 256, yy % 256, (xx + yy) % 256], -1).astype(np.uint8)
            im = Image.fromarray(a)
        tampon = io.BytesIO()
        im.save(tampon, format="PNG")
        return tampon.getvalue()

    def arreter(self) -> None:
        self.serveur.shutdown()
