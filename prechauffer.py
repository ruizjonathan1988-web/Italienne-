#!/usr/bin/env python3
"""
Préchauffage Azure Speech → Firebase Storage
Les Tréteaux du Babouin
"""

import sys, json, os, hashlib, re, time
import requests

# ════════════════════════════════════════════
AZURE_KEY    = "BgcgGqWCWbTOA874yi6JZvEVd5dA66HGbbk56PymWZ5WB1hmtainJQQJ99CEAC5T7U2XJ3w3AAAYACOGLjE9"
AZURE_REGION = "francecentral"
FIREBASE_BUCKET  = "italienne-33180.appspot.com"
FIREBASE_API_KEY = "AIzaSyD6iOgKg_8cQiXzGPSiWDVaXU2ey02nqJk"
# ════════════════════════════════════════════

VOIX = [
    "fr-FR-DeniseNeural","fr-FR-HenriNeural","fr-FR-EloiseNeural",
    "fr-FR-BrigitteNeural","fr-FR-CelesteNeural","fr-FR-ClaudeNeural",
    "fr-FR-CoralieNeural","fr-FR-JacquelineNeural","fr-FR-JeromeNeural",
    "fr-FR-JosephineNeural","fr-FR-MauriceNeural","fr-FR-YvetteNeural",
    "fr-FR-RemyMultilingualNeural","fr-FR-VivienneMultilingualNeural",
    "fr-CA-SylvieNeural","fr-CA-JeanNeural","fr-CA-AntoineNeural",
    "fr-CA-ThierryNeural","fr-BE-GerardNeural","fr-BE-CharlineNeural",
]

def lire_pdf(path):
    try:
        import fitz
        doc = fitz.open(path)
        texte = "".join(page.get_text() for page in doc)
        doc.close()
        return texte
    except ImportError:
        print("pip install pymupdf")
        sys.exit(1)

def parse_script(texte):
    lignes = []
    DIAL_RE = re.compile(r'^([A-ZÀÂÇÉÈÊËÎÏÔÛÙÜŒÆ][A-ZÀÂÇÉÈÊËÎÏÔÛÙÜŒÆ\s\-\'\.]{0,40}?)\s*:\s*(.+)$')
    for ligne in texte.split('\n'):
        ligne = ligne.strip()
        if not ligne or len(ligne) < 4: continue
        m = DIAL_RE.match(ligne)
        if m:
            role = m.group(1).strip()
            texte_r = m.group(2).strip()
            if len(role) >= 2 and len(texte_r) >= 2:
                lignes.append({'role': role, 'text': texte_r})
    return lignes

def nettoyer(text):
    """Nettoyer le texte pour SSML"""
    replacements = {
        '…': '...', '\u2019': "'", '\u2018': "'",
        '\u00ab': '"', '\u00bb': '"', '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '-', '\u00a0': ' ',
        '&': '&amp;', '<': '&lt;', '>': '&gt;',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.strip()

def azure_tts(text, voice_name):
    """Appel Azure Speech REST API via requests"""
    text_clean = nettoyer(text)
    if not text_clean:
        raise ValueError("Texte vide après nettoyage")
    
    ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='fr-FR'><voice name='{voice_name}'>{text_clean}</voice></speak>"""
    
    url = f"https://{AZURE_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        'Ocp-Apim-Subscription-Key': AZURE_KEY,
        'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'audio-24khz-48kbitrate-mono-mp3',
    }
    r = requests.post(url, headers=headers, data=ssml.encode('utf-8'), timeout=20)
    if r.status_code != 200:
        raise Exception(f"Azure {r.status_code}: {r.text[:100]}")
    return r.content

def sauvegarder_local(audio_bytes, cache_key):
    """Sauvegarder le MP3 localement dans tts_cache/"""
    os.makedirs('tts_cache', exist_ok=True)
    safe_key = hashlib.sha1(cache_key.encode()).hexdigest()
    path = os.path.join('tts_cache', f"{safe_key}.mp3")
    with open(path, 'wb') as f:
        f.write(audio_bytes)
    return path

def main():
    if len(sys.argv) < 2:
        print("Usage: python prechauffer.py script.pdf")
        sys.exit(1)

    script_file = sys.argv[1]
    if not os.path.exists(script_file):
        print(f"Fichier introuvable : {script_file}")
        sys.exit(1)

    ext = os.path.splitext(script_file)[1].lower()
    print(f"Lecture : {script_file}")
    texte = lire_pdf(script_file) if ext == '.pdf' else open(script_file, encoding='utf-8', errors='ignore').read()

    lignes = parse_script(texte)
    if not lignes:
        print("Aucune réplique trouvée")
        sys.exit(1)

    print(f"✓ {len(lignes)} répliques trouvées")
    roles = list(dict.fromkeys(l['role'] for l in lignes))
    print(f"✓ {len(roles)} personnages : {', '.join(roles)}")

    voix_file = "voix.json"
    if os.path.exists(voix_file):
        with open(voix_file, encoding='utf-8') as f:
            voix_assign = json.load(f)
        print(f"✓ voix.json chargé")
    else:
        voix_assign = {role: VOIX[i % len(VOIX)] for i, role in enumerate(roles)}
        with open(voix_file, 'w', encoding='utf-8') as f:
            json.dump(voix_assign, f, ensure_ascii=False, indent=2)
        print(f"✓ voix.json créé — modifie-le si besoin puis relance")
        for r, v in voix_assign.items():
            print(f"   {r:20} → {v}")
        return

    print(f"\nPrechauffage en cours...\n")
    total = len(lignes)
    ok = erreurs = sautes = 0

    for i, ligne in enumerate(lignes):
        role = ligne['role']
        text = ligne['text']
        voice = voix_assign.get(role)

        if not voice:
            sautes += 1
            continue

        try:
            print(f"  [{i+1:3}/{total}] {role:15} : {text[:45]}...")
            audio = azure_tts(text, voice)
            cache_key = f"az||{voice}||{text}"
            sauvegarder_local(audio, cache_key)
            ok += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"    Erreur: {e}")
            erreurs += 1
            time.sleep(0.5)

    print(f"\n{'='*55}")
    print(f"✓ {ok} repliques prechauffees")
    if erreurs: print(f"  {erreurs} erreurs")
    print(f"La troupe peut maintenant utiliser les voix !")
    print(f"")
    print(f"ETAPE SUIVANTE : uploade le dossier tts_cache/ sur GitHub")
    print(f"  1. Va sur github.com/ruizjonathan1988-web/Italienne-")
    print(f"  2. Upload all files dans tts_cache/")
    print(f"  3. Commit changes")

if __name__ == '__main__':
    main()
