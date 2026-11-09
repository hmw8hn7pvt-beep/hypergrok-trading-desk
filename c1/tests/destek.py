"""İzole sınama sahnesi. Yalnız geçici dizin ve sentetik dosya."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
from dataclasses import dataclass, field

from c1.config import (
    MANIFEST_ADI,
    MK_ADLARI,
    R1_ADI,
    R2_ADI,
    NIHAI_ADI,
    DISK_YEDEK_BAYT,
    Mk,
    Mod,
    Yapilandirma,
)


def _yaz(yol: str, veri: bytes, izin: int) -> None:
    fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o644)
    try:
        os.write(fd, veri)
    finally:
        os.close(fd)
    os.chmod(yol, izin)


def _temizle(yol: str) -> None:
    if not os.path.exists(yol):
        return
    for kok, dizinler, dosyalar in os.walk(yol):
        for ad in dizinler:
            try:
                os.chmod(os.path.join(kok, ad), 0o700)
            except OSError:
                pass
        for ad in dosyalar:
            try:
                os.chmod(os.path.join(kok, ad), 0o600)
            except OSError:
                pass
    shutil.rmtree(yol)


@dataclass
class Dosya:
    ad: str
    icerik: bytes
    grup: str = "A"
    tur: str = "normal"
    izin: int = 0o644
    symlink_metin: str = ""
    sha256: str = ""


@dataclass
class Sahne:
    kok: str
    kaynak: str
    cikti: str
    cfg: Yapilandirma
    payload: str
    payload_icerik: bytes
    mk5: str
    a_ek: str | None = None
    disari: str | None = None
    ekstra: dict = field(default_factory=dict)

    def nihai(self) -> str:
        return os.path.join(self.cikti, self.cfg.nihai_adi)

    def r2(self) -> str:
        return os.path.join(self.cikti, self.cfg.r2_adi)

    def kapat(self) -> None:
        _temizle(self.kok)


def hazirla(
    kok: str,
    *,
    dosyalar: list[Dosya] | None = None,
    manifest: str = "iyi",
    a_ek: bool = False,
    traversal: bool = False,
    kacis: bool = False,
    yinelenen: bool = False,
    manifest_sabit: bool = False,
) -> Sahne:
    kaynak = os.path.join(kok, "src")
    cikti = os.path.join(kok, "out")
    os.mkdir(kaynak, 0o700)
    os.mkdir(cikti, 0o700)
    freeze = os.path.join(kaynak, "freeze")
    os.mkdir(freeze, 0o700)
    mk5 = os.path.join(kok, "mk5-dis", "C1_MK5_DOKUNULMAZ_bot_eki.md")
    os.mkdir(os.path.dirname(mk5), 0o700)
    _yaz(mk5, b"MK5-DOKUNMA\n", 0o644)
    govdeler = {
        "MK-1": b"kural-mk1\n",
        "MK-2": b"indirme-mk2\n",
        "MK-3": b"kosu-mk3\n",
        "MK-4": b"kayit-mk4\n",
    }
    ozetler = {anahtar: hashlib.sha256(veri).hexdigest() for anahtar, veri in govdeler.items()}
    for anahtar, veri in govdeler.items():
        _yaz(os.path.join(freeze, MK_ADLARI[anahtar]), veri, 0o444)
    yollar = {anahtar: os.path.join(freeze, MK_ADLARI[anahtar]) for anahtar in govdeler}
    if manifest == "eksik":
        satirlar = [f"{ozetler['MK-1']}  {yollar['MK-1']}\n", f"{ozetler['MK-2']}  {yollar['MK-2']}\n", f"{ozetler['MK-3']}  {yollar['MK-3']}\n", f"{ozetler['MK-4']}  {yollar['MK-4']}\n"]
    elif manifest == "fazla":
        satirlar = [f"{ozetler[k]}  {yollar[k]}\n" for k in ("MK-1", "MK-2", "MK-3", "MK-4")]
        satirlar.append(f"{'ab' * 32}  {mk5}\n")
        satirlar.append(f"{'cd' * 32}  {mk5}-fazla\n")
    else:
        mk1 = ozetler["MK-1"]
        if manifest == "bozuk":
            mk1 = ("0" if mk1[0] != "0" else "1") + mk1[1:]
        satirlar = [
            f"{mk1}  {yollar['MK-1']}\n",
            f"{ozetler['MK-2']}  {yollar['MK-2']}\n",
            f"{ozetler['MK-3']}  {yollar['MK-3']}\n",
            f"{ozetler['MK-4']}  {yollar['MK-4']}\n",
            f"{'ab' * 32}  {mk5}\n",
        ]
    _yaz(os.path.join(freeze, MANIFEST_ADI), "".join(satirlar).encode("utf-8"), 0o444)
    if dosyalar is None:
        dosyalar = [Dosya("veri/not.txt", b"merhaba")]
    olusan: list[tuple[Dosya, str]] = []
    for dosya in dosyalar:
        yol = os.path.join(kaynak, dosya.ad)
        os.makedirs(os.path.dirname(yol), 0o700, exist_ok=True)
        if dosya.tur == "symlink":
            os.symlink(dosya.symlink_metin, yol)
        else:
            _yaz(yol, dosya.icerik, dosya.izin)
        olusan.append((dosya, yol))
    a_ek_yol = None
    if a_ek:
        a_ek_yol = os.path.join(kaynak, "a_ek", "p34_collector.txt")
        os.makedirs(os.path.dirname(a_ek_yol), 0o700)
        _yaz(a_ek_yol, b"A-EK-DOKUNMA\n", 0o644)
    disari = None
    if kacis:
        disari = os.path.join(kok, "disari", "gizli.txt")
        os.makedirs(os.path.dirname(disari), 0o700)
        _yaz(disari, b"GIZLI-DISARI\n", 0o644)
        os.symlink(os.path.dirname(disari), os.path.join(kaynak, "kacis"))
    if traversal:
        disari = os.path.join(kok, "disari", "gizli.txt")
        os.makedirs(os.path.dirname(disari), exist_ok=True)
        if not os.path.exists(disari):
            _yaz(disari, b"GIZLI-TRAVERSAL\n", 0o644)
    envanter = os.path.join(kaynak, "C1_DOSYA_LISTESI.csv")
    with open(envanter, "w", encoding="utf-8", newline="") as fh:
        yazici = csv.writer(fh, lineterminator="\n")
        yazici.writerow(["yol", "grup", "tur", "izin", "boyut", "symlink_metin", "sha256"])
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
            veri = govdeler[anahtar]
            yazici.writerow([yollar[anahtar], "A", "normal", "0444", str(len(veri)), "", ""])
        manifest_yol = os.path.join(freeze, MANIFEST_ADI)
        boyut = os.path.getsize(manifest_yol)
        yazici.writerow([manifest_yol, "A", "normal", "0444", str(boyut), "", ""])
        for dosya, yol in olusan:
            if dosya.tur == "symlink":
                boyut_hucre = str(len(dosya.symlink_metin.encode("utf-8", "surrogateescape")))
            else:
                boyut_hucre = str(len(dosya.icerik))
            sha = dosya.sha256
            yazici.writerow([yol, dosya.grup, dosya.tur, f"{dosya.izin:04o}", boyut_hucre, dosya.symlink_metin, sha])
            if yinelenen:
                yazici.writerow([yol, dosya.grup, dosya.tur, f"{dosya.izin:04o}", boyut_hucre, dosya.symlink_metin, sha])
        if a_ek_yol:
            yazici.writerow([a_ek_yol, "A_ek_oneri", "normal", "0644", "13", "", ""])
        if traversal:
            yazici.writerow([kaynak + "/../disari/gizli.txt", "A", "normal", "0644", "1", "", ""])
        if kacis and disari:
            yazici.writerow([os.path.join(kaynak, "kacis", "gizli.txt"), "A", "normal", "0644", "13", "", ""])
    mk = {
        anahtar: Mk(anahtar, yollar[anahtar], ozetler[anahtar])
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4")
    }
    mk["MK-5"] = Mk("MK-5", mk5, None)
    cfg = Yapilandirma(
        mod=Mod.IZOLE,
        onay="",
        kaynak_kok=kaynak,
        envanter_yolu=envanter,
        cikti_ust=cikti,
        r1_adi=R1_ADI,
        r2_adi=R2_ADI,
        nihai_adi=NIHAI_ADI,
        r5_dizin=freeze,
        manifest_adi=MANIFEST_ADI,
        mk=mk,
        kapsam_sabitleri=False,
        manifest_sabitleri_zorunlu=manifest_sabit,
        disk_yedek_bayt=DISK_YEDEK_BAYT,
    )
    ilk = olusan[0][1] if olusan else ""
    icerik = olusan[0][0].icerik if olusan else b""
    return Sahne(
        kok=kok,
        kaynak=kaynak,
        cikti=cikti,
        cfg=cfg,
        payload=ilk,
        payload_icerik=icerik,
        mk5=mk5,
        a_ek=a_ek_yol,
        disari=disari,
    )


def arsiv_uyesi(yol: str, ad: str):
    import tarfile

    with tarfile.open(yol, "r") as tf:
        return tf.getmember(ad)
