"""R5 manifesti. MK-5 için dosya sistemi çağrısı yoktur.

Manifest SHA-256 ve 547 bayt, gerçek modda R1 sabitidir.
Bu karşılaştırma bağımsız bir doğrulama değildir.
MK-1..MK-4 hash'leri yalnız yapılandırmadan okunur.
"""

from __future__ import annotations

import os
import re

from c1.config import MANIFEST_BOYUT, MANIFEST_SHA256, Yapilandirma
from c1.errors import C1Error
from c1.hashing import ozet_bayt
from c1.inventory import Islem
from c1.secure_fs import Politika, bayt_oku, icerik_ac

_SATIR = re.compile(r"([0-9a-f]{64})  (.+)")


def _oku(yol: str, politika: Politika, dizinler: dict, islem: Islem | None) -> tuple[bytes, str]:
    referans = islem.meta if islem is not None else None
    icerik = icerik_ac(yol, politika, dizinler, referans, 17, 6)
    try:
        veri = bayt_oku(icerik)
        return veri, ozet_bayt(veri)
    finally:
        icerik.kapat()


def coz_manifest(veri: bytes) -> list[tuple[str, str]]:
    if b"\x00" in veri:
        raise C1Error(6, "3-B", "Manifest NUL içeriyor", "NUL yok", "NUL")
    try:
        metin = veri.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise C1Error(6, "3-B", "Manifest UTF-8 değil", "utf-8", str(exc)) from exc
    if not metin.endswith("\n"):
        raise C1Error(6, "3-B", "Manifest satır sonu yok", "\\n", "yok")
    satirlar = metin.splitlines()
    if len(satirlar) != 5:
        raise C1Error(6, "3-B", "Manifest satır sayısı", "5", str(len(satirlar)))
    sonuc: list[tuple[str, str]] = []
    for satir in satirlar:
        eslesme = _SATIR.fullmatch(satir)
        if not eslesme:
            raise C1Error(6, "3-B", "Manifest satır biçimi sha256sum metin değil", "64hex␠␠yol", satir)
        sonuc.append((eslesme.group(1), eslesme.group(2)))
    if len({yol for _, yol in sonuc}) != 5:
        raise C1Error(6, "3-B", "Manifest yolları yineleniyor", "5 benzersiz", "yinelenen")
    return sonuc


def manifest_yolunu_coz(ham: str, r5_dizin: str) -> str:
    """Göreli yol freeze dizinine göre çözülür. Sıra değil, çözülmüş küme kullanılır."""
    if not ham or "\x00" in ham:
        raise C1Error(6, "3-B", "Manifest yolu boş veya NUL", "yol", ham)
    if ham.startswith("/"):
        if os.path.normpath(ham) != ham:
            raise C1Error(6, "3-B", "Mutlak manifest yolu normal değil", ham, os.path.normpath(ham))
        return ham
    parca = ham.split("/")
    if any(p in ("", ".", "..") for p in parca):
        raise C1Error(6, "3-B", "Göreli manifest yolu geçersiz", "freeze altına göreli", ham)
    return r5_dizin + "/" + ham


def dogrula(
    cfg: Yapilandirma,
    politika: Politika,
    dizinler: dict,
    islemler: list[Islem],
) -> str:
    """0g / Adım 3. Manifest dosyası değiştirilmez."""
    by_yol = {k.yol: k for k in islemler}
    manifest_yol = cfg.manifest_yolu()
    if manifest_yol not in by_yol:
        raise C1Error(6, "0g", "Manifest işlem listesinde yok", manifest_yol, "yok")
    veri, ozet = _oku(manifest_yol, politika, dizinler, by_yol[manifest_yol])
    sabit_satir = "3a-0: manifest R1 sabiti bu çalışmada zorunlu değil"
    if cfg.manifest_sabitleri_zorunlu:
        if len(veri) != MANIFEST_BOYUT:
            raise C1Error(6, "3a-0", "Manifest boyutu R1 sabiti değil", str(MANIFEST_BOYUT), str(len(veri)))
        if ozet != MANIFEST_SHA256:
            raise C1Error(
                6,
                "3a-0",
                "Manifest SHA-256 R1 sabiti değil; bu karşılaştırma bağımsız doğrulama değildir",
                MANIFEST_SHA256,
                ozet,
            )
        sabit_satir = (
            "3a-0: manifest R1 sabitiyle karşılaştırıldı "
            "(bağımsız doğrulama değildir); boyut ve SHA-256 uydu"
        )
    satirlar = coz_manifest(veri)
    cozulmus = [(sha, manifest_yolunu_coz(yol, cfg.r5_dizin)) for sha, yol in satirlar]
    gelen = {yol for _, yol in cozulmus}
    beklenen = {cfg.mk[k].yol for k in ("MK-1", "MK-2", "MK-3", "MK-4", "MK-5")}
    if gelen != beklenen:
        raise C1Error(6, "3-B", "Manifest yol kümesi MK-1..MK-5 değil", sorted(beklenen), sorted(gelen))
    harita = {yol: sha for sha, yol in cozulmus}
    rapor = [sabit_satir, "3-B (iv): manifest bayt özgünlüğü doğrulanamadı"]
    for anahtar, asama in (("MK-1", "3a-1"), ("MK-2", "3a-1"), ("MK-3", "3a-1"), ("MK-4", "3a-2")):
        mk = cfg.mk[anahtar]
        if mk.yol not in by_yol:
            raise C1Error(6, asama, f"{anahtar} işlem listesinde yok", mk.yol, "yok")
        islem = by_yol[mk.yol]
        if islem.grup != "A" or islem.tur != "normal" or islem.izin != 0o444 or islem.meta is None or islem.meta.mod != 0o444:
            raise C1Error(6, "3b", f"{anahtar} 0444 Grup A normal dosya değil", "0444 A", islem.yol)
        if harita[mk.yol] != mk.sha256:
            raise C1Error(6, "3-B", f"{anahtar} manifest hash'i dış referans değil", mk.sha256, harita[mk.yol])
        _veri, dosya_ozet = _oku(mk.yol, politika, dizinler, islem)
        if dosya_ozet != mk.sha256:
            raise C1Error(6, asama, f"{anahtar} içerik hash'i dış referans değil", mk.sha256, dosya_ozet)
        rapor.append(f"{anahtar} hash uydu")
    mk5 = cfg.mk["MK-5"].yol
    if politika.dokunulmaz_mi(mk5) is False:
        raise C1Error(6, "MK-5", "MK-5 dokunulmaz kümede değil", "dokunulmaz", mk5)
    rapor.append(
        f"MK-5 yalnız metinsel yol: {mk5}. open/read/stat/lstat/hash/arşiv/envanter yok."
    )
    return "\n".join(rapor) + "\n"


def izin_raporu(cfg: Yapilandirma, islemler: list[Islem]) -> str:
    r5 = set(cfg.r5_yollari())
    k444 = [k for k in islemler if k.tur == "normal" and k.izin == 0o444]
    sapma = [k for k in k444 if k.meta is None or k.meta.mod != 0o444]
    for yol in cfg.r5_yollari():
        bulunan = [k for k in islemler if k.yol == yol]
        if len(bulunan) != 1 or bulunan[0].meta is None or bulunan[0].meta.mod != 0o444:
            raise C1Error(6, "3b", "R5 izni 0444 değil", "0444", yol)
    satirlar = ["R5 izin denetimi"]
    for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
        satirlar.append(f"{anahtar} {cfg.mk[anahtar].yol} 0444")
    satirlar.append(f"{cfg.manifest_adi} {cfg.manifest_yolu()} 0444")
    if sapma:
        ozet = f"3c: {len(k444) - len(sapma)}/{len(k444)} SAPMA"
        sonuc = "sonuç: SAPMA"
    else:
        ozet = f"3c: {len(k444)}/{len(k444)} (5 R5 dahil) değişmedi"
        sonuc = "sonuç: UYUM"
    satirlar.extend([ozet, sonuc])
    if len(satirlar) > 9:
        raise C1Error(12, "R5-izin", "R5_FREEZE_IZIN satır sınırı", "<=9", str(len(satirlar)))
    if not r5 <= {k.yol for k in k444}:
        raise C1Error(6, "3c", "K444 R5 dosyalarını içermiyor", "5", "eksik")
    if sapma:
        raise C1Error(6, "3c", "K444 izin sapması", "0444", sapma[0].yol)
    return "\n".join(satirlar) + "\n"
