"""İzole sınama sahnesi. Yalnız geçici dizin ve sentetik dosya."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field

from c1.config import (
    MANIFEST_ADI,
    MK_ADLARI,
    R1_ADI,
    R2_ADI,
    R3_ADI,
    NIHAI_ADI,
    DISK_YEDEK_BAYT,
    Mk,
    Mod,
    Yapilandirma,
    yukle,
)

# Gerçek ek: /home/box/agent-data/.../<64 onaltılık>.md
MK5_GOVDE_EK = (
    "agent-data/agents/06562474-4f5f-4279-a8d7-9a927d4cdc67/attachments/"
    "57c848d4fc3add9dd2fa1c76165c5780cbff8dd9cae338f3e65beec967a4930a.md"
)
YAPILANDIRMA_EK = "var/tmp/c1_r11_yapilandirma/c1_gercek.json"


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
    icerik: bytes = b""
    grup: str = "A_arastirma"
    tur: str = "file"
    izin: str = "0o644"
    symlink_hedef: str = ""
    mtime_trt: str = "2026-11-09 08:42:28"
    bayrak: str = ""
    notu: str = ""


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

    def gecici(self) -> str:
        return os.path.join(self.cikti, self.cfg.gecici_adi)

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
    manifest_ters: bool = False,
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
    mk1 = ozetler["MK-1"]
    if manifest == "bozuk":
        mk1 = ("0" if mk1[0] != "0" else "1") + mk1[1:]
    satirlar = [
        f"{mk1}  {MK_ADLARI['MK-1']}\n",
        f"{ozetler['MK-2']}  {MK_ADLARI['MK-2']}\n",
        f"{ozetler['MK-3']}  {MK_ADLARI['MK-3']}\n",
        f"{'ab' * 32}  {mk5}\n",
        f"{ozetler['MK-4']}  {MK_ADLARI['MK-4']}\n",
    ]
    if manifest == "eksik":
        satirlar = satirlar[:4]
    elif manifest == "fazla":
        satirlar.append(f"{'cd' * 32}  {mk5}-fazla\n")
    if manifest_ters:
        satirlar = list(reversed(satirlar))
    _yaz(os.path.join(freeze, MANIFEST_ADI), "".join(satirlar).encode("utf-8"), 0o444)
    if dosyalar is None:
        dosyalar = [Dosya("veri/not.txt", b"merhaba")]
    olusan: list[tuple[Dosya, str]] = []
    for dosya in dosyalar:
        yol = os.path.join(kaynak, dosya.ad)
        os.makedirs(os.path.dirname(yol), 0o700, exist_ok=True)
        if dosya.symlink_hedef:
            hedef = dosya.symlink_hedef
            if hedef == "@dizin":
                hedef = os.path.join(kaynak, "symlink_hedef_dizin")
                os.makedirs(hedef, 0o700, exist_ok=True)
                gizli = os.path.join(hedef, "gizli.txt")
                if not os.path.exists(gizli):
                    _yaz(gizli, b"GIZLI-HEDEF\n", 0o644)
            os.symlink(hedef, yol)
            dosya.symlink_hedef = hedef
        else:
            _yaz(yol, dosya.icerik, int(dosya.izin, 8))
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
        yazici.writerow(["grup", "yol", "tur", "boyut_bayt", "mtime_trt", "izin", "bayrak", "not"])
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
            veri = govdeler[anahtar]
            yazici.writerow(["A_arastirma", yollar[anahtar], "file", str(len(veri)), "2026-11-09 09:07:45", "0o444", "", ""])
        manifest_yol = os.path.join(freeze, MANIFEST_ADI)
        yazici.writerow(["A_arastirma", manifest_yol, "file", str(os.path.getsize(manifest_yol)), "2026-11-09 09:07:45", "0o444", "", ""])
        for dosya, yol in olusan:
            if dosya.symlink_hedef:
                tur_hucre, boyut_hucre = "symlink->" + dosya.symlink_hedef, "0"
            else:
                tur_hucre, boyut_hucre = "file", str(len(dosya.icerik))
            yazici.writerow([dosya.grup, yol, tur_hucre, boyut_hucre, dosya.mtime_trt, dosya.izin, dosya.bayrak, dosya.notu])
            if yinelenen:
                yazici.writerow([dosya.grup, yol, tur_hucre, boyut_hucre, dosya.mtime_trt, dosya.izin, dosya.bayrak, dosya.notu])
        if a_ek_yol:
            yazici.writerow(["A_ek_oneri", a_ek_yol, "file", "13", "2026-11-09 09:23:45", "0o644", "", "kapsam disi"])
        if traversal:
            yazici.writerow(["A_arastirma", kaynak + "/../disari/gizli.txt", "file", "1", "2026-11-09 08:42:28", "0o644", "", ""])
        if kacis and disari:
            yazici.writerow(["A_arastirma", os.path.join(kaynak, "kacis", "gizli.txt"), "file", "13", "2026-11-09 08:42:28", "0o644", "", ""])
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
        gecici_adi=R3_ADI,
        dokunulmaz_klasorler=(R1_ADI, R2_ADI),
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


def kur_gercek_duzen(kok: str) -> Sahne:
    """Gerçek yol düzenini geçici kök altında kurar ve yapılandırmayı yükler.

    kaynak = .../workspace
    envanter = .../workspace/hypergrok_v2_plan_20261109/C1_DOSYA_LISTESI.csv
    r5 = .../workspace/trading-desk-research-v1.7.1/research/intraday-r5-20261109/freeze
    çıktı = .../box
    MK-5 = .../box/agent-data/agents/.../attachments/<özet>.md
    yapılandırma = .../var/tmp/c1_r11_yapilandirma/c1_gercek.json
    """
    kaynak = os.path.join(kok, "workspace")
    cikti = os.path.join(kok, "box")
    freeze = os.path.join(
        kaynak, "trading-desk-research-v1.7.1", "research", "intraday-r5-20261109", "freeze"
    )
    os.makedirs(freeze, 0o700)
    os.mkdir(cikti, 0o700)
    mk5 = os.path.join(cikti, MK5_GOVDE_EK)
    os.makedirs(os.path.dirname(mk5), 0o700)
    _yaz(mk5, b"MK5-DOKUNMA\n", 0o644)
    r1 = os.path.join(cikti, R1_ADI)
    os.mkdir(r1, 0o700)
    _yaz(os.path.join(r1, "iz.txt"), b"KORU", 0o644)
    eski_r2 = os.path.join(cikti, R2_ADI)
    os.mkdir(eski_r2, 0o700)
    _yaz(os.path.join(eski_r2, "GUNLUK.txt"), b"ESKI-R2\n", 0o644)
    govdeler = {
        "MK-1": b"kural-mk1\n",
        "MK-2": b"indirme-mk2\n",
        "MK-3": b"kosu-mk3\n",
        "MK-4": b"kayit-mk4\n",
    }
    ozetler = {anahtar: hashlib.sha256(veri).hexdigest() for anahtar, veri in govdeler.items()}
    yollar = {}
    for anahtar, veri in govdeler.items():
        yol = os.path.join(freeze, MK_ADLARI[anahtar])
        _yaz(yol, veri, 0o444)
        yollar[anahtar] = yol
    satirlar = [
        f"{ozetler['MK-1']}  {MK_ADLARI['MK-1']}\n",
        f"{ozetler['MK-2']}  {MK_ADLARI['MK-2']}\n",
        f"{ozetler['MK-3']}  {MK_ADLARI['MK-3']}\n",
        f"{'ab' * 32}  {mk5}\n",
        f"{ozetler['MK-4']}  {MK_ADLARI['MK-4']}\n",
    ]
    manifest = os.path.join(freeze, MANIFEST_ADI)
    _yaz(manifest, "".join(satirlar).encode("utf-8"), 0o444)
    payload = os.path.join(kaynak, "veri", "not.txt")
    os.makedirs(os.path.dirname(payload), 0o700)
    _yaz(payload, b"merhaba", 0o644)
    hedef = os.path.join(kaynak, "bybit_research_v2val_rls6_20261109_0952")
    os.mkdir(hedef, 0o700)
    _yaz(os.path.join(hedef, "gizli.txt"), b"GIZLI-HEDEF\n", 0o644)
    bag = os.path.join(kaynak, "bybit_v2val_rls6_20261109")
    os.symlink(hedef, bag)
    envanter = os.path.join(kaynak, "hypergrok_v2_plan_20261109", "C1_DOSYA_LISTESI.csv")
    os.makedirs(os.path.dirname(envanter), 0o700)
    with open(envanter, "w", encoding="utf-8", newline="") as fh:
        yazici = csv.writer(fh, lineterminator="\n")
        yazici.writerow(["grup", "yol", "tur", "boyut_bayt", "mtime_trt", "izin", "bayrak", "not"])
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
            yazici.writerow(["A_arastirma", yollar[anahtar], "file", str(len(govdeler[anahtar])), "2026-11-09 09:07:45", "0o444", "", ""])
        yazici.writerow(["A_arastirma", manifest, "file", str(os.path.getsize(manifest)), "2026-11-09 09:07:45", "0o444", "", ""])
        yazici.writerow(["A_arastirma", payload, "file", "7", "2026-11-09 08:42:28", "0o644", "", ""])
        yazici.writerow(["A_arastirma", bag, "symlink->" + hedef, "0", "2026-11-09 09:59:10", "0o777", "ADDA_TARIH_2026-11-09_CALISMA_TARIHI_VERI_DEGIL", ""])
    json_yol = os.path.join(kok, YAPILANDIRMA_EK)
    os.makedirs(os.path.dirname(json_yol), 0o700)
    govde = {
        "kaynak_kok": kaynak,
        "envanter_yolu": envanter,
        "cikti_ust": cikti,
        "gecici_adi": R3_ADI,
        "dokunulmaz_klasorler": [R1_ADI, R2_ADI],
        "nihai_adi": NIHAI_ADI,
        "r5_dizin": freeze,
        "manifest_adi": MANIFEST_ADI,
        "mk": {
            "MK-1": {"sha256": ozetler["MK-1"]},
            "MK-2": {"sha256": ozetler["MK-2"]},
            "MK-3": {"sha256": ozetler["MK-3"]},
            "MK-4": {"sha256": ozetler["MK-4"]},
            "MK-5": {"yol": mk5},
        },
    }
    _yaz(json_yol, json.dumps(govde).encode("utf-8"), 0o644)
    cfg = yukle(json_yol, gercek=False, onay="", izole=True)
    return Sahne(
        kok=kok,
        kaynak=kaynak,
        cikti=cikti,
        cfg=cfg,
        payload=payload,
        payload_icerik=b"merhaba",
        mk5=mk5,
        ekstra={
            "json": json_yol,
            "agent_data": os.path.join(cikti, "agent-data"),
            "r1": r1,
            "eski_r2": eski_r2,
            "bag": bag,
            "hedef": hedef,
        },
    )


def arsiv_uyesi(yol: str, ad: str):
    import tarfile

    with tarfile.open(yol, "r") as tf:
        return tf.getmember(ad)
