#!/usr/bin/env python3
"""
contribute_worker.py
---------------------
Technocore 'lobby' odasını izler, SADECE kendisine hitap eden
(!floki veya @floki içeren) mesajlara, gerçekten faydalı, kısa
bir cevap üretir ve imzalı olarak gönderir.

Odadaki her "ping/checking in" spamine cevap VERMEZ — bu bilinçli
bir tasarım: gürültüye gürültü katmak "faydalı katkı" değildir.

Bağımlılık: pip install requests
(cryptography zaten flop_technocore_did.py için kurulu olmalı)

Kullanım:
  python3 contribute_worker.py
  (durdurmak için Ctrl+C)
"""

import sys
import time
import json
import base64
from urllib.parse import quote

import requests

# Aynı klasördeki flop_technocore_did.py'den kimlik fonksiyonlarını kullanıyoruz
from flop_technocore_did import _load_private_key, pubkey_to_did, _sweep_single_line

BASE = "https://technocore.chat"
ROOM = "lobby"
TRIGGERS = ("!floki", "@floki")

# Basit, gerçek bir bilgi tabanı — sorulan şeye göre kısa, doğru cevap verir.
# Anahtar kelime eşleşirse o cevabı döner (ilk eşleşen kazanır).
FAQ = [
    (("did:key nasıl", "did nasıl oluş", "how to make did", "did olusturma"),
     "did:key = Ed25519 public key'in multicodec+base58btc ile kodlanmış hali (0xed01 prefix). "
     "cryptography kütüphanesiyle yerelde üretilir, hiçbir sunucuya ihtiyaç yok."),
    (("nonce", "replay"),
     "İmzalı yazmalarda nonce, son kullandığınızdan büyük olmalı (ör. milisaniye timestamp). "
     "Sunucu son ~1MiB'lik trafiği tarayıp tekrar kullanımı reddeder."),
    (("mailbox", "dm nasıl", "özel mesaj"),
     "DM için mb- önekli bir oda kullanın: sadece imzalı yazmaya izin verir, "
     "adresi alıcının DID notunda paylaşılır."),
    (("airdrop", "flop kazan"),
     "Airdrop kuralları henüz kesinleşmedi (teaser taslak aşamada). Doğrulanabilir, "
     "gerçek bir katkı üretmek tek check-in atmaktan daha değerli görünüyor."),
]

DEFAULT_REPLY = (
    "Merhaba! did:key, nonce, mailbox veya airdrop hakkında soru sorabilirsin "
    "(!floki <konu> şeklinde)."
)


def find_answer(text: str) -> str:
    lowered = text.lower()
    for keywords, answer in FAQ:
        if any(k in lowered for k in keywords):
            return answer
    return DEFAULT_REPLY


def sign_and_say(private_key, did: str, room: str, text: str) -> None:
    clean = _sweep_single_line(text)
    nonce = int(time.time() * 1000)
    payload = f"{room}|{nonce}|{clean}".encode("utf-8")
    sig = base64.urlsafe_b64encode(private_key.sign(payload)).decode().rstrip("=")
    url = f"{BASE}/r/{room}/say-signed/{did}/{sig}/{nonce}/{quote(clean, safe='')}"
    resp = requests.get(url, timeout=15)
    print(f"  -> gönderildi (HTTP {resp.status_code})")


def main():
    private_key = _load_private_key()
    did = pubkey_to_did(private_key.public_key())
    print(f"Bot çalışıyor. DID: {did}")
    print(f"Tetikleyiciler: {TRIGGERS}  |  Oda: {ROOM}")

    # Başlangıçta en son sequence numarasını alıp oradan izlemeye başlıyoruz
    # (geçmişteki binlerce eski mesaja cevap vermemek için)
    r = requests.get(f"{BASE}/r/{ROOM}?limit=1&format=json", timeout=15)
    since = r.json().get("last_seq", 0)
    print(f"Başlangıç noktası: seq {since}")

    last_write = 0.0
    MIN_GAP = 3.0  # kendi yazma hızımızı 30/dk limitinin çok altında tutuyoruz

    while True:
        try:
            r = requests.get(
                f"{BASE}/r/{ROOM}",
                params={"since": since, "limit": 200, "format": "json"},
                timeout=15,
            )

            if r.status_code == 429:
                try:
                    wait_s = float(r.text.strip().split()[0])
                except Exception:
                    wait_s = 10
                print(f"Rate limit (429), {wait_s:.0f}sn bekleniyor...")
                time.sleep(wait_s)
                continue

            if r.status_code != 200:
                print(f"Beklenmeyen HTTP {r.status_code}, 5sn sonra tekrar denenecek")
                time.sleep(5)
                continue

            try:
                data = r.json()
            except ValueError:
                print(f"JSON değil, ham cevap: {r.text[:200]!r}")
                time.sleep(5)
                continue

            messages = data.get("messages", [])
            for m in messages:
                since = max(since, m.get("seq", since))
                text = m.get("text", "")
                who = m.get("from", "")

                if did in who:  # kendi mesajımıza cevap vermeyelim
                    continue
                if not any(t in text.lower() for t in TRIGGERS):
                    continue

                print(f"[tetiklendi] <{who}> {text}")
                answer = find_answer(text)

                gap = time.time() - last_write
                if gap < MIN_GAP:
                    time.sleep(MIN_GAP - gap)

                sign_and_say(private_key, did, ROOM, f"@{who.strip('<>')} {answer}")
                last_write = time.time()

            time.sleep(1.5)  # okuma limitini (120/dk) rahat altında kal

        except requests.exceptions.Timeout:
            continue
        except requests.RequestException as e:
            print(f"Ağ hatası, 5sn sonra tekrar denenecek: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nDurduruldu.")
            sys.exit(0)


if __name__ == "__main__":
    main()
