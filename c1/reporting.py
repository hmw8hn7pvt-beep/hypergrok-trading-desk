"""Türkçe raporlar. RAPOR.txt kapanıştan önce yazılır."""

from __future__ import annotations

from dataclasses import dataclass

from c1.config import KARANTINA_SONLARI, PYTHON_GERCEK, Yapilandirma
from c1.errors import C1Error
from c1.inventory import Islem
from c1.secure_fs import SyncKaydi, ac_cikti_cift, kapat, yaz_tampon
from c1.validation import rapor_butcesi


@dataclass
class Sonuc:
    durum: str
    ozet: str
    k5_hata: str | None = None
    nihai_yol: str | None = None
    r2_yol: str | None = None


class Gunluk:
    def __init__(self, rfd: int, kayitlar: list[SyncKaydi], butce: int) -> None:
        self.wfd, self.kayit = ac_cikti_cift(rfd, "GUNLUK.txt", kayitlar)
        self.butce = butce
        self.bayt = 0

    def satir(self, metin: str) -> None:
        veri = (metin.rstrip("\n") + "\n").encode("utf-8", "surrogateescape")
        if self.bayt + len(veri) > self.butce:
            raise C1Error(12, "günlük", "Günlük satır sınırı aşıldı", str(self.butce), str(self.bayt + len(veri)))
        yaz_tampon(self.wfd, veri)
        self.bayt += len(veri)

    def kapat(self) -> None:
        if self.wfd >= 0:
            kapat(self.wfd)
            self.wfd = -1


def kuru_ozet(cfg: Yapilandirma, surum: str) -> str:
    return (
        "DURUM: DRY-RUN\n"
        "Kaynaklara, envantere ve çıktı köküne erişilmedi.\n"
        f"Çalışan Python: {surum}\n"
        f"Kart Python: {PYTHON_GERCEK}\n"
        "Gerçek mod ancak --gercek ve --onay \"ONAY C-1\" birlikte verilirse açılır.\n"
        "Bu sürüm kart sürümü değilse gerçek mod, dizin açmadan koşul 1 ile durur.\n"
        f"Yapılandırılan kaynak kökü: {cfg.kaynak_kok}\n"
        f"Yapılandırılan çıktı üstü: {cfg.cikti_ust}\n"
        f"R2 adı: {cfg.r2_adi}\n"
        f"Nihai ad: {cfg.nihai_adi}\n"
        "R1 açılmaz ve yeniden kullanılmaz.\n"
    )


def rapor_metni(
    *,
    n: int,
    d: int,
    l_max: int,
    lk: int,
    max_h: int,
    max_x: int,
    x_buyuk: int,
    t_arsiv: int,
    r_deger: int,
    k444: int,
    r5_icinde: int,
    symlink_var: bool,
) -> str:
    symlink = "symlink metni: DOLAYLI DOĞRULANDI" if symlink_var else "symlink yok"
    metin = (
        f"N={n}\n"
        f"D={d}\n"
        f"L_max={l_max}\n"
        f"LK={lk}\n"
        f"max H_i={max_h}\n"
        f"max X_i={max_x}\n"
        f"X_i>2048 üye sayısı={x_buyuk}\n"
        f"T_arsiv={t_arsiv}\n"
        f"R={r_deger}\n"
        "YG: GEÇTİ\n"
        f"K444 = {k444} ({r5_icinde} R5 dahil)\n"
        f"{symlink}\n"
        "fazla dosya kontrolü yapılmadı\n"
        "manifest bayt özgünlüğü doğrulanamadı\n"
        "B1 ve B2 KARANTİNA: içerik yorumlanmaz\n"
        "Kapanış: henüz yapılmadı\n"
    )
    butce = rapor_butcesi(l_max)
    if len(metin.encode("utf-8")) > butce:
        raise C1Error(12, "rapor", "Rapor satır sınırı aşıldı", str(butce), str(len(metin)))
    return metin


def teslim_metni(durum: str, k1: str, k2: str, k3: str, k4: str) -> str:
    return (
        f"K1: {k1}\n"
        f"K2: {k2}\n"
        f"K3: {k3}\n"
        f"K4: {k4}\n"
        "K5: TESLIM_BILDIRIMI yazıldı\n"
        f"durum: {durum}\n"
        "K5 hatası teslim durumunu değiştirmez.\n"
        "RAPOR.txt kapanıştan önce yazıldı ve kapanışın henüz yapılmadığını söyler.\n"
    )


def karantina_metni(islemler: list[Islem], gercek: bool) -> str:
    satirlar = ["KARANTİNA: B1 ve B2 içerik olarak yorumlanmaz."]
    for son in KARANTINA_SONLARI:
        var = any(k.grup == "B1" and (k.yol.endswith(son) or k.arcname.endswith(son)) for k in islemler)
        satirlar.append(f"{son}: {'var' if var else 'yok'}")
        if gercek and not var:
            raise C1Error(2, "karantina", "Gerçek modda karantina kaydı eksik", son, "yok")
    return "\n".join(satirlar) + "\n"


def manifest_metni(islemler: list[Islem], grup: str) -> str:
    satirlar = []
    for kayit in islemler:
        if kayit.grup != grup:
            continue
        etiket = "DOLAYLI" if kayit.tur == "symlink" else "DOGRUDAN"
        satirlar.append(f"{kayit.sha1}  {kayit.arcname}  {etiket}")
    return ("\n".join(satirlar) + "\n") if satirlar else ""


def denetim_metni(satirlar: list[str]) -> str:
    return "\n".join(satirlar) + "\n"
