# Installation de LOCAL-IMAGE-IA sous Windows 11 (GPU NVIDIA).
# Fichier volontairement sans accents : PowerShell 5.1 lit mal l'UTF-8 sans BOM.
#
# Ce que fait ce script, dans l'ordre :
#   1. verifie le pilote NVIDIA et l'espace disque ;
#   2. telecharge ComfyUI portable (archive officielle) et l'extrait dans moteur\ ;
#   3. telecharge les 3 fichiers du modele FLUX.2 klein 4B (Apache 2.0), avec reprise,
#      et verifie leur taille et leur empreinte SHA-256 ;
#   4. cree boite\entree, boite\sortie, boite\archive et config.json ;
#   5. verifie que le Python de ComfyUI fait tourner LOCAL-IMAGE-IA.
# Liens, tailles et empreintes verifies le 7 octobre 2026.
# Relancer le script est sans danger : ce qui est deja en place est conserve.

param(
    [switch]$SansVerificationSha
)

$ErrorActionPreference = "Stop"
$Racine = Split-Path $PSScriptRoot -Parent
$Moteur = Join-Path $Racine "moteur"
$Portable = Join-Path $Moteur "ComfyUI_windows_portable"
$Py = Join-Path $Portable "python_embeded\python.exe"
$UrlComfy = "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"

$Modeles = @(
    @{ Dossier = "diffusion_models"; Nom = "flux-2-klein-4b-fp8.safetensors"; Taille = 4070624520;
       Sha = "97ed34fe0567e436200f2faee3939b88f2b5d99f8af2a4dc16532c4245c0ccb6";
       Url = "https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/resolve/main/flux-2-klein-4b-fp8.safetensors" },
    @{ Dossier = "text_encoders"; Nom = "qwen_3_4b.safetensors"; Taille = 8044982048;
       Sha = "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a";
       Url = "https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors" },
    @{ Dossier = "vae"; Nom = "flux2-vae.safetensors"; Taille = 336213556;
       Sha = "d64f3a68e1cc4f9f4e29b6e0da38a0204fe9a49f2d4053f0ec1fa1ca02f9c4b5";
       Url = "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors" }
)

function Etape([string]$Texte) { Write-Host ""; Write-Host "== $Texte" -ForegroundColor Cyan }
function Arret([string]$Texte) {
    Write-Host ""
    Write-Host "ARRET DECLARE : $Texte" -ForegroundColor Red
    exit 1
}

function Telecharger([string]$Url, [string]$Destination) {
    $Partiel = "$Destination.part"
    # curl.exe est fourni avec Windows 10 et 11 ; -C - reprend un telechargement interrompu.
    & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $Partiel $Url
    if ($LASTEXITCODE -ne 0) { Arret "Telechargement echoue ($Url). Verifie la connexion et relance : il reprendra ou il s'est arrete." }
    Move-Item -Force $Partiel $Destination
}

Etape "1. Carte graphique et disque"
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    Arret "nvidia-smi introuvable : installe ou mets a jour le pilote NVIDIA (application NVIDIA ou nvidia.com/drivers), redemarre, puis relance."
}
& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
$Lecteur = (Get-Item $Racine).PSDrive.Name
$Libre = [math]::Round((Get-PSDrive $Lecteur).Free / 1GB, 1)
Write-Host "Espace libre sur ${Lecteur}: $Libre Go"
if ($Libre -lt 25) { Arret "Il faut environ 25 Go libres (ComfyUI ~5 Go, modele ~12,5 Go, marge). Libere de la place ou deplace le dossier." }
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Arret "curl.exe introuvable (normalement fourni avec Windows 10/11)." }

Etape "2. ComfyUI portable"
if (Test-Path (Join-Path $Portable "ComfyUI\main.py")) {
    Write-Host "Deja installe : $Portable"
} else {
    New-Item -ItemType Directory -Force $Moteur | Out-Null
    $Archive = Join-Path $Moteur "ComfyUI_windows_portable_nvidia.7z"
    if (-not (Test-Path $Archive)) { Telecharger $UrlComfy $Archive }
    Write-Host "Extraction (quelques minutes)..."
    Push-Location $Moteur
    & tar.exe -xf $Archive
    $Code = $LASTEXITCODE
    Pop-Location
    if ($Code -ne 0 -or -not (Test-Path (Join-Path $Portable "ComfyUI\main.py"))) {
        Arret "Extraction impossible avec tar. Ouvre $Archive avec 7-Zip (7-zip.org) ou l'explorateur Windows, extrais-le dans $Moteur (il doit contenir ComfyUI_windows_portable), puis relance ce script."
    }
    Remove-Item $Archive
}

Etape "3. Modele FLUX.2 klein 4B (environ 12,5 Go)"
foreach ($M in $Modeles) {
    $Dossier = Join-Path $Portable "ComfyUI\models\$($M.Dossier)"
    New-Item -ItemType Directory -Force $Dossier | Out-Null
    $Fichier = Join-Path $Dossier $M.Nom
    if ((Test-Path $Fichier) -and ((Get-Item $Fichier).Length -eq $M.Taille)) {
        Write-Host "Deja present : $($M.Nom)"
    } else {
        Write-Host "Telechargement : $($M.Nom)"
        Telecharger $M.Url $Fichier
    }
    if ((Get-Item $Fichier).Length -ne $M.Taille) { Arret "$($M.Nom) : taille inattendue. Supprime le fichier et relance." }
    # Une empreinte deja verifiee n'est pas recalculee (plusieurs minutes pour 8 Go).
    $Temoin = "$Fichier.sha256-ok"
    $DejaVerifie = (Test-Path $Temoin) -and ((Get-Content $Temoin -Raw).Trim() -eq $M.Sha) -and
                   ((Get-Item $Temoin).LastWriteTime -ge (Get-Item $Fichier).LastWriteTime)
    if (-not $SansVerificationSha -and -not $DejaVerifie) {
        Write-Host "Verification de l'empreinte SHA-256 de $($M.Nom) (quelques minutes)..."
        $Sha = (Get-FileHash -Algorithm SHA256 $Fichier).Hash.ToLower()
        if ($Sha -ne $M.Sha) { Arret "$($M.Nom) : empreinte inattendue ($Sha). Supprime le fichier et relance." }
        Set-Content -Path $Temoin -Value $M.Sha -Encoding ASCII
    }
}

Etape "4. Boite de depot et reglages"
foreach ($D in @("entree", "sortie", "archive")) { New-Item -ItemType Directory -Force (Join-Path $Racine "boite\$D") | Out-Null }
$Config = Join-Path $Racine "config.json"
if (-not (Test-Path $Config)) { Copy-Item (Join-Path $Racine "config.exemple.json") $Config }
Write-Host "Depose tes demandes dans : $(Join-Path $Racine 'boite\entree')"

Etape "5. Verification de LOCAL-IMAGE-IA"
# Toute la sortie est lue (2>&1) : la couper avec Select-Object faisait echouer Python
# en cours d'ecriture, et l'erreur reelle n'etait pas affichee.
# PowerShell 5.1 transforme chaque ligne d'erreur d'un programme en exception quand
# ErrorActionPreference vaut Stop : on lit d'abord tout, on juge ensuite sur le code.
$ErrorActionPreference = "Continue"
$Sortie = & $Py (Join-Path $Racine "lancer.py") verifier 2>&1
$Code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
$Sortie | ForEach-Object { Write-Host "  $_" }
if ($Code -ne 0) {
    Arret "Le Python de ComfyUI n'arrive pas a lancer LOCAL-IMAGE-IA (code $Code). Copie les lignes ci-dessus et envoie-les."
}

Write-Host ""
Write-Host "Installation terminee." -ForegroundColor Green
Write-Host "Etape suivante : double-clic sur windows\diagnostic.bat (mesure les temps), puis windows\demarrer.bat."
