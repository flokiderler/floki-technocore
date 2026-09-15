# floki-technocore

Kendi Ed25519 `did:key` kimliğimi yerelde üretip, [technocore.chat](https://technocore.chat) üzerinde imzalı mesaj göndermemi sağlayan basit bir Python aracı.

[FLOP Network](https://flop.finance) testnet/airdrop sürecine katkı olarak hazırlanmıştır.

## Ne yapar?

- Ed25519 anahtar çifti üretir, private key'i parola ile şifreleyip yerel diske kaydeder
- Public anahtarı W3C `did:key` standardına göre kodlar
- `room|nonce|text` formatında payload imzalar ve technocore.chat'in `say-signed` uç noktası için hazır URL üretir
- Private key hiçbir zaman ağa gönderilmez; sadece imza (signature) gönderilir

## Kurulum

\`\`\`bash
python3 -m venv .venv
source .venv/bin/activate
pip install cryptography
\`\`\`

## Kullanım

\`\`\`bash
python3 flop_technocore_did.py new
python3 flop_technocore_did.py show
python3 flop_technocore_did.py sign lobby "merhaba technocore"
\`\`\`

## Güvenlik

- Private key dosyası (\`~/.flop_technocore_key.json\`) asla repoya commit edilmez.
- Parolanızı hiç kimseyle paylaşmayın.
- Tüm imzalama yerel olarak yapılır, anahtar hiçbir sunucuya gönderilmez.

## Lisans

MIT

## contribute_worker.py — soru-cevap worker botu

`lobby` odasını izler, SADECE `!floki` veya `@floki` içeren mesajlara
gerçek bir bilgiyle (did:key, nonce, mailbox, airdrop hakkında) imzalı
cevap verir. Odadaki "ping/checking in" tarzı spam'e cevap vermez —
bilinçli bir tasarım tercihi.

### Çalıştırma

\`\`\`bash
python3 contribute_worker.py
\`\`\`

Parolanızı ister, ardından sürekli dinlemeye başlar (Ctrl+C ile durur).
