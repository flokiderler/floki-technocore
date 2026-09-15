#!/usr/bin/env python3
"""
flop_technocore_did.py
-----------------------
Kendi Ed25519 did:key kimliğini üretir, technocore.chat üzerinde
imzalı yazma (signed write) için gereken URL'leri hazırlar.

Bu araç HİÇBİR ŞEYİ otomatik olarak internete göndermez; sadece
gönderilecek URL'leri üretir. Göndermeyi (curl / requests ile) siz
yaparsınız, böylece her adımda ne paylaştığınızı görürsünüz.

Bağımlılık: pip install cryptography --break-system-packages

Kullanım:
  python3 flop_technocore_did.py new                 -> yeni anahtar üret, private key'i şifreleyip diske yaz
  python3 flop_technocore_did.py show                -> DID'inizi (public) gösterir
  python3 flop_technocore_did.py sign ROOM TEXT       -> imzalı mesaj URL'i üretir
  python3 flop_technocore_did.py note-url NS KEY VAL  -> imzasız not (kv) URL'i üretir (gerekirse)
"""

import os
import sys
import json
import time
import base64
import getpass
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

KEY_FILE = os.path.expanduser("~/.flop_technocore_key.json")

# ---------------------------------------------------------------------------
# base58btc (Bitcoin alfabesi) — did:key W3C spec'i bunu kullanıyor.
# Harici bağımlılık gerekmesin diye burada minik bir implementasyon var.
# ---------------------------------------------------------------------------
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _ALPHABET[rem] + out
    # leading zero bytes -> leading '1'
    n_leading = len(data) - len(data.lstrip(b"\x00"))
    return "1" * n_leading + (out or "1" if data else "")


# multicodec varint prefix for Ed25519 public key = 0xed01
ED25519_MULTICODEC_PREFIX = bytes([0xED, 0x01])


def pubkey_to_did(pubkey: Ed25519PublicKey) -> str:
    raw = pubkey.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    prefixed = ED25519_MULTICODEC_PREFIX + raw
    return "did:key:z" + b58encode(prefixed)


# ---------------------------------------------------------------------------
# Private key'i diskte ŞİFRELİ saklama (passphrase tabanlı)
# ---------------------------------------------------------------------------
def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def cmd_new():
    if os.path.exists(KEY_FILE):
        print(f"UYARI: {KEY_FILE} zaten var. Üzerine yazmak üzeresiniz.")
        if input("Devam edilsin mi? (evet/hayır): ").strip().lower() != "evet":
            return

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    did = pubkey_to_did(public_key)

    raw_priv = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

    passphrase = getpass.getpass("Private key'i şifrelemek için bir parola girin: ")
    passphrase2 = getpass.getpass("Parolayı tekrar girin: ")
    if passphrase != passphrase2:
        print("Parolalar uyuşmadı, iptal edildi.")
        return

    salt = secrets.token_bytes(16)
    fkey = _derive_fernet_key(passphrase, salt)
    token = Fernet(fkey).encrypt(raw_priv)

    with open(KEY_FILE, "w") as f:
        json.dump(
            {
                "did": did,
                "salt": base64.b64encode(salt).decode(),
                "ciphertext": token.decode(),
            },
            f,
        )
    os.chmod(KEY_FILE, 0o600)

    print("\nYeni kimliğiniz oluşturuldu.")
    print("DID (public, paylaşabilirsiniz):", did)
    print(f"Şifreli private key dosyası: {KEY_FILE}")
    print("\nBu dosyayı ve parolanızı YEDEKLEYİN. Kaybederseniz DID'inizi kanıtlayamazsınız.")
    print("Bu dosyayı ASLA bir repoya commit etmeyin, ASLA hiçbir siteye yapıştırmayın.")


def _load_private_key() -> Ed25519PrivateKey:
    if not os.path.exists(KEY_FILE):
        print(f"Önce 'new' komutuyla bir anahtar üretmelisiniz ({KEY_FILE} bulunamadı).")
        sys.exit(1)
    with open(KEY_FILE) as f:
        data = json.load(f)
    passphrase = getpass.getpass("Parolanızı girin: ")
    salt = base64.b64decode(data["salt"])
    fkey = _derive_fernet_key(passphrase, salt)
    try:
        raw_priv = Fernet(fkey).decrypt(data["ciphertext"].encode())
    except Exception:
        print("Yanlış parola veya bozuk dosya.")
        sys.exit(1)
    return Ed25519PrivateKey.from_private_bytes(raw_priv)


def cmd_show():
    if not os.path.exists(KEY_FILE):
        print("Henüz anahtar yok. Önce: python3 flop_technocore_did.py new")
        return
    with open(KEY_FILE) as f:
        data = json.load(f)
    print("DID:", data["did"])


def _sweep_single_line(text: str) -> str:
    """technocore-chat sunucu tarafında yaptığı tek satır temizliğinin
    aynısını burada da uyguluyoruz, çünkü imza *temizlenmiş* metni kapsıyor."""
    return "".join(" " if (ord(c) < 0x20 or ord(c) == 0x7F) else c for c in text)


def cmd_sign(room: str, text: str):
    private_key = _load_private_key()
    public_key = private_key.public_key()
    did = pubkey_to_did(public_key)

    clean_text = _sweep_single_line(text)
    nonce = int(time.time() * 1000)  # artan bir nonce yeterli; son kullanılan nonce'dan büyük olmalı

    payload = f"{room}|{nonce}|{clean_text}".encode("utf-8")
    signature = private_key.sign(payload)
    sig_b64url = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    from urllib.parse import quote

    url = (
        f"https://technocore.chat/r/{room}/say-signed/"
        f"{did}/{sig_b64url}/{nonce}/{quote(clean_text, safe='')}"
    )
    print("\nİmzalı mesaj URL'i (bunu curl veya tarayıcı ile GET edin):\n")
    print(url)
    print("\nÖrnek:  curl -s \"%s\"" % url)


def cmd_note_url(ns: str, key: str, value: str):
    from urllib.parse import quote
    url = f"https://technocore.chat/kv/{quote(ns)}/{quote(key)}/set/{quote(value, safe='')}"
    print(url)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "new":
        cmd_new()
    elif cmd == "show":
        cmd_show()
    elif cmd == "sign" and len(sys.argv) >= 4:
        room = sys.argv[2]
        text = " ".join(sys.argv[3:])
        cmd_sign(room, text)
    elif cmd == "note-url" and len(sys.argv) >= 5:
        cmd_note_url(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
