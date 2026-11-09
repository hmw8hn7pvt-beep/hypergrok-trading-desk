"""Çalışma yapılandırması.

Gerçek kart yolları burada sabit dizgidir. Bu modül onları açmaz.
Dış R5 hash'leri kodda yoktur; yapılandırma dosyasından okunur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
import re

from c1.errors import C1Error

ONAY_METIN = "ONAY C-1"
PYTHON_GERCEK = "3.13.5"
MANIFEST_BOYUT = 547
MANIFEST_SHA256 = "a98b9dc8c7742f9588da23e6a670d7f5f138407953d1a7a835b27a1cfaf5ca02"
DISK_YEDEK_BAYT = 2 * 1024 * 1024 * 1024

YASAK_KOKLER = ("/workspace", "/home/box")

ENVANTER_N = 2908
ISLEM_N = 2897
GRUP_SAYILARI = {"A": 1936, "B1": 910, "B2": 51}
NORMAL_N = 2896
SYMLINK_N = 1
A_EK_N = 11
K444_N = 216

R1_ADI = "GECERSIZ_c1_arsiv_20261110"
R2_ADI = "GECERSIZ_c1_arsiv_20261110_R2"
NIHAI_ADI = "c1_arsiv_20261110"

GERCEK_KAYNAK_KOK = "/workspace"
GERCEK_ENVANTER = "/workspace/hypergrok_v2_plan_20261109/C1_DOSYA_LISTESI.csv"
GERCEK_CIKTI_UST = "/home/box"
GERCEK_R5_DIZIN = "/workspace/trading-desk-research-v1.7.1/research/intraday-r5-20261109/freeze"
MANIFEST_ADI = "SHA256SUMS.txt"

MK_ADLARI = {
    "MK-1": "R5_FROZEN_RULES.md",
    "MK-2": "DOWNLOAD_SPEC_R5.md",
    "MK-3": "RUN_SPEC_R5.md",
    "MK-4": "FREEZE_RECORD.txt",
}
MK_ANAHTARLARI = ("MK-1", "MK-2", "MK-3", "MK-4", "MK-5")
ARSIV_ADLARI = {
    "A": "A_arastirma.tar",
    "B1": "B1_karantina.tar",
    "B2": "B2_karantina.tar",
}
GRUPLAR = ("A", "B1", "B2")
KARANTINA_SONLARI = (
    "briefs/BTC-20261108-224608-770980-TRT.md",
    "briefs/BTC-20261108-224608-770980-TRT.raw.json",
    "data/scan-20261109/Hyperliquid_tek_seferlik_tarama_2026-11-09.zip",
)

_SHA = re.compile(r"[0-9a-f]{64}")
_CSV_BASLIK = ("yol", "grup", "tur", "izin", "boyut", "symlink_metin", "sha256")


class Mod(Enum):
    DRY_RUN = "dry-run"
    IZOLE = "izole"
    GERCEK = "gercek"


def csv_baslik() -> tuple[str, ...]:
    return _CSV_BASLIK


def sha_biçimli(deger: str) -> bool:
    return bool(_SHA.fullmatch(deger))


def _tek_bilesen(ad: str, etiket: str) -> None:
    if not ad or "/" in ad or ad in (".", "..") or "\x00" in ad:
        raise C1Error(1, "yapılandırma", f"{etiket} tek bileşen değil", "tek bileşen", ad)


def _kok(yol: str, etiket: str) -> None:
    if not yol.startswith("/") or yol.endswith("/") or "\x00" in yol:
        raise C1Error(2, "yapılandırma", f"{etiket} mutlak yol değil", "mutlak yol", yol)
    if os.path.normpath(yol) != yol:
        raise C1Error(2, "yapılandırma", f"{etiket} normalleştirilmemiş", yol, os.path.normpath(yol))
    parca = yol.split("/")
    if any(p in ("", ".", "..") for p in parca[1:]):
        raise C1Error(2, "yapılandırma", f"{etiket} bileşeni geçersiz", "geçerli bileşen", yol)


def yasak_kok_mu(yol: str) -> bool:
    for kok in YASAK_KOKLER:
        if yol == kok or yol.startswith(kok + "/"):
            return True
    return False


@dataclass
class Mk:
    anahtar: str
    yol: str
    sha256: str | None


@dataclass
class Yapilandirma:
    mod: Mod
    onay: str
    kaynak_kok: str
    envanter_yolu: str
    cikti_ust: str
    r1_adi: str
    r2_adi: str
    nihai_adi: str
    r5_dizin: str
    manifest_adi: str
    mk: dict[str, Mk]
    kapsam_sabitleri: bool
    manifest_sabitleri_zorunlu: bool
    disk_yedek_bayt: int
    dokunulmaz: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        _kok(self.kaynak_kok, "kaynak_kok")
        _kok(self.cikti_ust, "cikti_ust")
        _kok(self.envanter_yolu, "envanter_yolu")
        _kok(self.r5_dizin, "r5_dizin")
        for etiket, ad in (
            ("r1_adi", self.r1_adi),
            ("r2_adi", self.r2_adi),
            ("nihai_adi", self.nihai_adi),
            ("manifest_adi", self.manifest_adi),
        ):
            _tek_bilesen(ad, etiket)
        if len({self.r1_adi, self.r2_adi, self.nihai_adi}) != 3:
            raise C1Error(1, "yapılandırma", "R1, R2 ve nihai adlar ayrı olmalı", "3 ad", "çakışma")
        if self.kaynak_kok == self.cikti_ust or self.kaynak_kok.startswith(self.cikti_ust + "/") or self.cikti_ust.startswith(self.kaynak_kok + "/"):
            raise C1Error(1, "yapılandırma", "Kaynak ve çıktı kökleri ayrık olmalı", "ayrık", self.cikti_ust)
        if not (self.envanter_yolu == self.kaynak_kok or self.envanter_yolu.startswith(self.kaynak_kok + "/")):
            raise C1Error(2, "yapılandırma", "Envanter kaynak kökünün altında değil", self.kaynak_kok, self.envanter_yolu)
        if not self.r5_dizin.startswith(self.kaynak_kok + "/"):
            raise C1Error(2, "yapılandırma", "R5 dizini kaynak kökünün altında değil", self.kaynak_kok, self.r5_dizin)
        if set(self.mk) != set(MK_ANAHTARLARI):
            raise C1Error(6, "yapılandırma", "MK anahtar kümesi eksik", list(MK_ANAHTARLARI), sorted(self.mk))
        manifest = self.manifest_yolu()
        if not manifest.startswith(self.r5_dizin + "/"):
            raise C1Error(6, "yapılandırma", "Manifest R5 dizininde değil", self.r5_dizin, manifest)
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
            kayit = self.mk[anahtar]
            if kayit.yol != self.r5_dizin + "/" + MK_ADLARI[anahtar]:
                raise C1Error(6, "yapılandırma", f"{anahtar} yolu kart adıyla uyuşmuyor", MK_ADLARI[anahtar], kayit.yol)
            if self.mod is not Mod.DRY_RUN and not sha_biçimli(kayit.sha256 or ""):
                raise C1Error(6, "yapılandırma", f"{anahtar} hash yapılandırmada yok", "64 onaltılık", kayit.sha256)
        mk5 = self.mk["MK-5"]
        _kok(mk5.yol, "MK-5")
        if mk5.yol.startswith(self.kaynak_kok + "/") or mk5.yol == self.kaynak_kok:
            raise C1Error(6, "yapılandırma", "MK-5 kaynak kökünün içinde olamaz", "kaynak dışı", mk5.yol)
        for ad in (self.r1_adi, self.r2_adi, self.nihai_adi):
            sinir = self.cikti_ust + "/" + ad
            if mk5.yol == sinir or mk5.yol.startswith(sinir + "/"):
                raise C1Error(
                    6,
                    "yapılandırma",
                    "MK-5 R1, R2 veya nihai klasörün içinde olamaz",
                    "bu klasörlerin dışı",
                    mk5.yol,
                )
        if mk5.sha256 is not None:
            raise C1Error(6, "yapılandırma", "MK-5 hash'i kodda veya yapılandırmada doğrulanmaz", "yok", "var")
        self.dokunulmaz.add(mk5.yol)
        if self.mod is Mod.GERCEK:
            self._gercek_kilit()
        elif self.mod is Mod.IZOLE:
            self._izole_kilit()
        if self.disk_yedek_bayt < 0:
            raise C1Error(3, "yapılandırma", "Disk yedeği negatif", ">=0", self.disk_yedek_bayt)

    def _gercek_kilit(self) -> None:
        if self.onay != ONAY_METIN:
            raise C1Error(1, "onay", "Gerçek mod onayı yok", ONAY_METIN, self.onay)
        beklenen = {
            "kaynak_kok": (self.kaynak_kok, GERCEK_KAYNAK_KOK),
            "envanter": (self.envanter_yolu, GERCEK_ENVANTER),
            "cikti_ust": (self.cikti_ust, GERCEK_CIKTI_UST),
            "r1": (self.r1_adi, R1_ADI),
            "r2": (self.r2_adi, R2_ADI),
            "nihai": (self.nihai_adi, NIHAI_ADI),
            "r5": (self.r5_dizin, GERCEK_R5_DIZIN),
            "manifest": (self.manifest_adi, MANIFEST_ADI),
        }
        for ad, (gelen, kart) in beklenen.items():
            if gelen != kart:
                raise C1Error(1, "yapılandırma", f"Gerçek {ad} kartla uyuşmuyor", kart, gelen)
        if not self.kapsam_sabitleri or not self.manifest_sabitleri_zorunlu:
            raise C1Error(1, "yapılandırma", "Gerçek modda kapsam ve manifest sabitleri zorunlu", "açık", "kapalı")
        if self.disk_yedek_bayt < DISK_YEDEK_BAYT:
            raise C1Error(3, "yapılandırma", "Gerçek mod disk yedeği 2 GiB altında", DISK_YEDEK_BAYT, self.disk_yedek_bayt)
        for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
            if not sha_biçimli(self.mk[anahtar].sha256 or ""):
                raise C1Error(6, "yapılandırma", f"{anahtar} hash'i yapılandırmadan okunamadı", "64 onaltılık", self.mk[anahtar].sha256)

    def _izole_kilit(self) -> None:
        if self.onay == ONAY_METIN:
            raise C1Error(1, "onay", "İzole mod gerçek onay metnini taşıyamaz", "onaysız", self.onay)
        for yol in (self.kaynak_kok, self.cikti_ust, self.envanter_yolu, self.r5_dizin, self.mk["MK-5"].yol):
            if yasak_kok_mu(yol):
                raise C1Error(1, "kapsam", "İzole mod yasak kökü açamaz", "geçici dizin", yol)

    def manifest_yolu(self) -> str:
        return self.r5_dizin + "/" + self.manifest_adi

    def r5_yollari(self) -> tuple[str, ...]:
        return tuple(self.mk[k].yol for k in ("MK-1", "MK-2", "MK-3", "MK-4")) + (self.manifest_yolu(),)

    def izinli_mi(self, yol: str) -> bool:
        for kok in (self.kaynak_kok, self.cikti_ust):
            if yol == kok or yol.startswith(kok + "/"):
                return True
        return False


def _mk_kur(ham: dict[str, object], r5_dizin: str) -> dict[str, Mk]:
    if not isinstance(ham, dict):
        raise C1Error(6, "yapılandırma", "mk alanı nesne değil", "nesne", type(ham).__name__)
    sonuc: dict[str, Mk] = {}
    for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4"):
        dugum = ham.get(anahtar)
        if not isinstance(dugum, dict) or "sha256" not in dugum:
            raise C1Error(6, "yapılandırma", f"{anahtar} sha256 alanı yok", "sha256", dugum)
        sha = dugum["sha256"]
        if not isinstance(sha, str):
            raise C1Error(6, "yapılandırma", f"{anahtar} sha256 metin değil", "metin", type(sha).__name__)
        sonuc[anahtar] = Mk(anahtar, r5_dizin + "/" + MK_ADLARI[anahtar], sha.strip().lower())
    dugum5 = ham.get("MK-5")
    if not isinstance(dugum5, dict) or "yol" not in dugum5:
        raise C1Error(6, "yapılandırma", "MK-5 yol alanı yok", "yol", dugum5)
    if "sha256" in dugum5:
        raise C1Error(6, "yapılandırma", "MK-5 hash alanı taşınamaz", "yalnız yol", "sha256")
    yol5 = dugum5["yol"]
    if not isinstance(yol5, str):
        raise C1Error(6, "yapılandırma", "MK-5 yolu metin değil", "metin", type(yol5).__name__)
    sonuc["MK-5"] = Mk("MK-5", yol5, None)
    return sonuc


def _bayrak(ham: dict[str, object], anahtar: str, varsayilan: bool) -> bool:
    """Anahtar yoksa varsayılan. Gerçek modda kapsam ve manifest anahtarı boşsa açıktır."""
    if anahtar not in ham:
        return varsayilan
    return bool(ham[anahtar])


def yukle(yol: str, *, gercek: bool, onay: str, izole: bool) -> Yapilandirma:
    """JSON yapılandırmasını okur. Onay kapısı dosya açılmadan çalışır.

    Gerçek dosya `/var/tmp/c1_r11_yapilandirma/c1_gercek.json` olabilir.
    Bu yol yasak köklerin dışındadır ve açılabilir.
    """
    if gercek and izole:
        raise C1Error(1, "onay", "Gerçek ve izole birlikte seçilemez", "tek mod", "ikisi")
    if gercek and onay != ONAY_METIN:
        raise C1Error(1, "onay", "Gerçek mod reddedildi", ONAY_METIN, onay)
    if yasak_kok_mu(yol):
        raise C1Error(1, "kapsam", "Yapılandırma dosyası yasak kökte olamaz", "kaynak dışı", yol)
    if gercek:
        mod = Mod.GERCEK
    elif izole:
        mod = Mod.IZOLE
    else:
        mod = Mod.DRY_RUN
    try:
        fd = os.open(yol, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        raise C1Error(1, "yapılandırma", "Yapılandırma dosyası açılamadı", yol, exc.strerror) from exc
    try:
        parca = []
        while True:
            buf = os.read(fd, 1024 * 1024)
            if not buf:
                break
            parca.append(buf)
            if sum(map(len, parca)) > 1024 * 1024:
                raise C1Error(1, "yapılandırma", "Yapılandırma dosyası çok büyük", "<=1MiB", ">1MiB")
    finally:
        os.close(fd)
    try:
        ham = json.loads(b"".join(parca).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise C1Error(1, "yapılandırma", "Yapılandırma JSON değil", "json", str(exc)) from exc
    if not isinstance(ham, dict):
        raise C1Error(1, "yapılandırma", "Yapılandırma nesne değil", "nesne", type(ham).__name__)
    r5 = str(ham.get("r5_dizin", ""))
    try:
        mk = _mk_kur(ham.get("mk", {}), r5)
    except C1Error:
        raise
    return Yapilandirma(
        mod=mod,
        onay=onay,
        kaynak_kok=str(ham.get("kaynak_kok", "")),
        envanter_yolu=str(ham.get("envanter_yolu", "")),
        cikti_ust=str(ham.get("cikti_ust", "")),
        r1_adi=str(ham.get("r1_adi", "")),
        r2_adi=str(ham.get("r2_adi", "")),
        nihai_adi=str(ham.get("nihai_adi", "")),
        r5_dizin=r5,
        manifest_adi=str(ham.get("manifest_adi", "")),
        mk=mk,
        kapsam_sabitleri=_bayrak(ham, "kapsam_sabitleri", gercek),
        manifest_sabitleri_zorunlu=_bayrak(ham, "manifest_sabitleri_zorunlu", gercek),
        disk_yedek_bayt=int(ham.get("disk_yedek_bayt", DISK_YEDEK_BAYT)),
    )
