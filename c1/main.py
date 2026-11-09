"""C-1 çalıştırma. Varsayılan DRY-RUN. Gerçek mod açık onay ister.

Bu program borsa emri göndermez. Kaynak dosyaya yazmaz.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import platform
import sys

from c1 import archive_validator, archive_writer, commit, inventory, metadata, reporting, secure_fs
from c1.config import (
    ARSIV_ADLARI,
    GRUPLAR,
    PYTHON_GERCEK,
    Mod,
    Yapilandirma,
    yukle,
)
from c1.errors import C1Error
from c1.hashing import ozet_bayt, ozet_dolayli
from c1.inventory import Islem
from c1.r5_validation import dogrula as r5_dogrula
from c1.r5_validation import izin_raporu
from c1.secure_fs import Politika, SyncKaydi
from c1.validation import (
    bayt_uzunluk,
    dizin_kumesi,
    gunluk_butcesi,
    h_ust_sinir,
    r_hesabi,
    tar_grup_boyutu,
)


class Baglam:
    def __init__(self, cfg: Yapilandirma, pfd: int, p0: tuple[int, int], rfd: int, r0: tuple[int, int]) -> None:
        self.cfg = cfg
        self.pfd = pfd
        self.p0 = p0
        self.rfd = rfd
        self.r0 = r0
        self.sync: list[SyncKaydi] = []
        self.gunluk: reporting.Gunluk | None = None

    def yaz(self, ad: str, metin: str) -> None:
        veri = metin.encode("utf-8", "surrogateescape")
        if veri and not veri.endswith(b"\n"):
            veri += b"\n"
        secure_fs.yaz_dosya(self.rfd, ad, veri, self.sync)

    def kapat_hepsi(self) -> None:
        hatalar: list[BaseException] = []

        def dene(fn) -> None:
            try:
                fn()
            except BaseException as exc:  # kapatma hatası da kayda geçer
                hatalar.append(exc)

        if self.gunluk is not None:
            dene(self.gunluk.kapat)
        for kayit in self.sync:
            if kayit.fd >= 0:
                fd = kayit.fd
                kayit.fd = -1
                dene(lambda fd=fd: secure_fs.kapat(fd))
        if self.rfd >= 0:
            fd = self.rfd
            self.rfd = -1
            dene(lambda: secure_fs.kapat(fd))
        if self.pfd >= 0:
            fd = self.pfd
            self.pfd = -1
            dene(lambda: secure_fs.kapat(fd))
        if hatalar:
            raise hatalar[0]


def _betik_boyutu() -> int:
    kok = os.path.dirname(os.path.abspath(__file__))
    toplam = 0
    for ad in os.listdir(kok):
        if ad.endswith(".py"):
            toplam += os.stat(os.path.join(kok, ad)).st_size
    return toplam


def _v_ust(islemler: list[Islem]) -> dict[str, int]:
    sonuc = {grup: 0 for grup in GRUPLAR}
    for kayit in islemler:
        lk = bayt_uzunluk(kayit.symlink_metin) if kayit.tur == "symlink" else 0
        baslik = h_ust_sinir(bayt_uzunluk(kayit.yol), kayit.tur == "symlink", lk)
        if kayit.tur == "symlink":
            veri = 0
        else:
            veri = ((kayit.boyut_envanter + 511) // 512) * 512
        sonuc[kayit.grup] += baslik + veri
    return sonuc


def _v_kesin(islemler: list[Islem]) -> tuple[dict[str, int], int, int, int]:
    sonuc = {grup: 0 for grup in GRUPLAR}
    max_h = 0
    max_x = 0
    buyuk = 0
    for kayit in islemler:
        if kayit.meta is None:
            raise C1Error(3, "0c2", "Kesin disk hesabında metadata yok", kayit.yol, "yok")
        kayit.h_i = archive_writer.olc_h(kayit)
        x_i = kayit.h_i - 512
        max_h = max(max_h, kayit.h_i)
        max_x = max(max_x, x_i)
        if x_i > 2048:
            buyuk += 1
        if kayit.tur == "symlink":
            veri = 0
        else:
            veri = ((kayit.meta.boyut + 511) // 512) * 512
        sonuc[kayit.grup] += kayit.h_i + veri
    return sonuc, max_h, max_x, buyuk


def _disk_yeter(pfd: int, v_grup: dict[str, int], r_deger: int, yedek: int, asama: str) -> int:
    t_arsiv = sum(tar_grup_boyutu(v) for v in v_grup.values())
    ihtiyac = t_arsiv + r_deger + yedek
    bos = secure_fs.bos_alan(pfd)
    if bos < ihtiyac:
        raise C1Error(3, asama, "Disk alanı yetersiz", str(ihtiyac), str(bos))
    return t_arsiv


def _islem_csv(islemler: list[Islem]) -> str:
    buf = io.StringIO()
    yazici = csv.writer(buf, lineterminator="\n")
    yazici.writerow(["yol", "arcname", "grup", "grup_ham", "tur", "izin", "boyut_bayt", "mtime_trt", "bayrak", "not"])
    for kayit in islemler:
        yazici.writerow([
            kayit.yol, kayit.arcname, kayit.grup, kayit.grup_ham, kayit.tur,
            f"0o{kayit.izin:o}", kayit.boyut_envanter, kayit.mtime_trt, kayit.bayrak, kayit.not_alani,
        ])
    return buf.getvalue()


def _hash_al(kayit: Islem, politika: Politika, dizinler: dict, kosul: int) -> str:
    if kayit.tur == "symlink":
        if kayit.meta is None:
            raise C1Error(10, "S-A", "Symlink metadatası yok", kayit.yol, "yok")
        metadata.sa_kontrol(kayit.symlink_metin, kayit.meta.boyut)
        return ozet_dolayli(kayit.symlink_metin)
    icerik = secure_fs.icerik_ac(kayit.yol, politika, dizinler, kayit.meta, 17, kosul)
    try:
        return secure_fs.hash_oku(icerik)
    finally:
        icerik.kapat()


def _akis(ctx: Baglam, politika: Politika, deneme: str) -> reporting.Sonuc:
    cfg = ctx.cfg
    ctx.gunluk = reporting.Gunluk(ctx.rfd, ctx.sync, gunluk_butcesi(1, 1))
    gunluk = ctx.gunluk
    gunluk.satir("0a platform")
    ctx.yaz(
        "PLATFORM_KONTROL.txt",
        "\n".join(
            [
                f"Python: {platform.python_version()}",
                f"Kart Python: {PYTHON_GERCEK}",
                f"mod: {cfg.mod.value}",
                deneme,
                "Dokunulmaz önceki klasörler açılmadı: " + ",".join(cfg.dokunulmaz_klasorler),
                f"Geçici: {cfg.gecici_adi}",
                "O_NOFOLLOW O_NOATIME O_PATH O_DIRECTORY O_CLOEXEC: var",
                "çıktı yolu mutlak açılmaz; RFD üzerinden yazılır",
            ]
        )
        + "\n",
    )
    metin, meta_envanter, zincir = inventory.oku(cfg, politika)
    islemler, a_ek, ham = inventory.coz(metin, cfg)
    gunluk.butce = gunluk_butcesi(max(len(islemler), 1), max((bayt_uzunluk(k.yol) for k in islemler), default=1))
    gunluk.satir(f"0b envanter satır={ham} işlem={len(islemler)} A-ek={len(a_ek)}")
    ctx.yaz(
        "C1_OKUMA.txt",
        "\n".join(
            [
                f"envanter_bayt={meta_envanter.boyut}",
                f"envanter_dev={meta_envanter.dev}",
                f"envanter_ino={meta_envanter.ino}",
                f"zincir_bilesen={len(zincir)}",
                f"ham={ham}",
                f"islem={len(islemler)}",
                f"A-ek={len(a_ek)}",
                "YG: GEÇTİ",
                "A-ek ve MK-5 için dosya sistemi işlemi yok",
            ]
        )
        + "\n",
    )
    ctx.yaz("ISLEM_LISTESI.csv", _islem_csv(islemler))
    dizin_yollari = dizin_kumesi([k.yol for k in islemler])
    uzunluklar = [bayt_uzunluk(k.yol) for k in islemler] or [0]
    l_max = max(uzunluklar)
    lk = max((bayt_uzunluk(k.symlink_metin) for k in islemler if k.tur == "symlink"), default=0)
    derinlik = max((k.yol.count("/") for k in islemler), default=0)
    n = len(islemler)
    d = len(dizin_yollari)
    r_deger = r_hesabi(n, d, l_max, derinlik, lk, _betik_boyutu())
    t_ust = _disk_yeter(ctx.pfd, _v_ust(islemler), r_deger, cfg.disk_yedek_bayt, "0c1")
    gunluk.satir(f"0c1 T_ust={t_ust} R={r_deger}")
    dizinler = metadata.dizinleri_kaydet(dizin_yollari, politika)
    ctx.yaz("ONCESI_DIZIN_METADATA.csv", metadata.csv_dizin(dizinler))
    gunluk.satir(f"0d dizin={len(dizinler)}")
    for kayit in islemler:
        metadata.dosya_kaydet(kayit, politika, dizinler)
    ctx.yaz("ONCESI_METADATA.csv", metadata.csv_dosya(islemler))
    gunluk.satir("0e metadata")
    v_kesin, max_h, max_x, x_buyuk = _v_kesin(islemler)
    t_arsiv = _disk_yeter(ctx.pfd, v_kesin, r_deger, cfg.disk_yedek_bayt, "0c2")
    gunluk.satir(f"0c2 T_arsiv={t_arsiv}")
    for kayit in islemler:
        metadata.noatime_dene(kayit, politika, dizinler)
    ctx.yaz(
        "NOATIME_TEST.csv",
        "yol,sonuc\n" + "".join(f"{k.yol},TAMAM\n" for k in islemler),
    )
    gunluk.satir("0f O_NOATIME")
    r5_metin = r5_dogrula(cfg, politika, dizinler, islemler)
    ctx.yaz("R5_FREEZE_HASH.txt", r5_metin)
    ctx.yaz("R5_FREEZE_IZIN.txt", izin_raporu(cfg, islemler))
    gunluk.satir("0g R5")
    secure_fs.asama_arasi("adim1-oncesi")
    metadata.dizinleri_karsilastir(dizin_yollari, politika, dizinler, 7)
    metadata.dosyalari_karsilastir(islemler, politika, dizinler, 7)
    gunluk.satir("adım 1 metadata aynı")
    for kayit in islemler:
        kayit.sha1 = _hash_al(kayit, politika, dizinler, 16)
    for grup in GRUPLAR:
        ctx.yaz(f"{grup}_kaynak_1.sha256", reporting.manifest_metni(islemler, grup))
    gunluk.satir("adım 2 kaynak hash")
    secure_fs.asama_arasi("adim4-oncesi", islemler)
    arsiv_ozet: list[str] = []
    for grup in GRUPLAR:
        secilen = [k for k in islemler if k.grup == grup]
        veri, uyeler, sync = archive_writer.yaz_arsiv(
            ctx.rfd, ARSIV_ADLARI[grup], secilen, politika, dizinler, ctx.sync
        )
        archive_validator.dogrula_tampon(veri, uyeler, cfg.kaynak_kok, set(a_ek))
        ozet = ozet_bayt(veri)
        secure_fs.fchmod_arsiv(sync)
        arsiv_ozet.append(f"{ozet}  {ARSIV_ADLARI[grup]}")
        del veri
    ctx.yaz("ARSIV_HASHLERI.sha256", "\n".join(arsiv_ozet) + "\n")
    ctx.yaz("KARANTINA_3.txt", reporting.karantina_metni(islemler, cfg.mod is Mod.GERCEK))
    gunluk.satir("adım 4-5 arşiv doğrulandı")
    metadata.dosyalari_karsilastir(islemler, politika, dizinler, 16)
    for kayit in islemler:
        ikinci = _hash_al(kayit, politika, dizinler, 16)
        if ikinci != kayit.sha1:
            raise C1Error(16, "6b", "İkinci kaynak hash'i ilkinden farklı", kayit.sha1, ikinci)
    for grup in GRUPLAR:
        ctx.yaz(f"{grup}_kaynak_2.sha256", reporting.manifest_metni(islemler, grup))
    metadata.dizinleri_karsilastir(dizin_yollari, politika, dizinler, 17)
    ctx.yaz("SONRASI_METADATA.csv", metadata.csv_dosya(islemler))
    ctx.yaz("SONRASI_DIZIN_METADATA.csv", metadata.csv_dizin(dizinler))
    ctx.yaz("KAYNAK_DENETIM.txt", reporting.denetim_metni([f"UYUM\t{k.yol}" for k in islemler]))
    ctx.yaz("DIZIN_DENETIM.txt", reporting.denetim_metni([f"UYUM\t{yol}" for yol in dizin_yollari]))
    gunluk.satir("adım 6 kaynak değişmedi")
    k444 = [k for k in islemler if k.tur == "normal" and k.izin == 0o444]
    r5_ic = sum(1 for k in k444 if k.yol in set(cfg.r5_yollari()))
    ctx.yaz(
        "RAPOR.txt",
        reporting.rapor_metni(
            n=n,
            d=d,
            l_max=l_max,
            lk=lk,
            max_h=max_h,
            max_x=max_x,
            x_buyuk=x_buyuk,
            t_arsiv=t_arsiv,
            r_deger=r_deger,
            k444=len(k444),
            r5_icinde=r5_ic,
            symlink_var=any(k.tur == "symlink" for k in islemler),
        ),
    )
    gunluk.satir("RAPOR yazıldı; kapanış henüz yapılmadı")
    gunluk.kapat()
    k1 = commit.k1()
    k2 = commit.k2(ctx.rfd, ctx.sync, ctx.r0)
    k3 = commit.k3(ctx.pfd, ctx.rfd, cfg.gecici_adi, cfg.nihai_adi, ctx.p0, ctx.r0)
    durum = commit.k4(ctx.pfd, ctx.p0)
    metin = reporting.teslim_metni(durum, k1, k2, k3, durum)
    k5_hata = None
    try:
        commit.k5(ctx, metin)
    except Exception as exc:
        k5_hata = exc.satir() if isinstance(exc, C1Error) else str(exc)
        try:
            ctx.kapat_hepsi()
        except Exception as kapatma:
            k5_hata = f"{k5_hata} | kapatma={kapatma}"
    return reporting.Sonuc(
        durum=durum,
        ozet=metin if k5_hata is None else metin + f"K5_HATA: {k5_hata}\n",
        k5_hata=k5_hata,
        nihai_yol=cfg.cikti_ust + "/" + cfg.nihai_adi,
        r2_yol=cfg.cikti_ust + "/" + cfg.gecici_adi,
    )


def calistir(cfg: Yapilandirma) -> reporting.Sonuc:
    if cfg.mod is Mod.DRY_RUN:
        return reporting.Sonuc(durum="DRY-RUN", ozet=reporting.kuru_ozet(cfg, platform.python_version()))
    if cfg.mod is Mod.GERCEK:
        secure_fs.dikisleri_dogrula()
        gelen = platform.python_version()
        if gelen != PYTHON_GERCEK:
            raise C1Error(1, "0a", "Python sürümü kartla uyuşmuyor", PYTHON_GERCEK, gelen)
    elif cfg.mod is not Mod.IZOLE:
        raise C1Error(1, "mod", "Bilinmeyen mod", "dry-run|izole|gercek", cfg.mod)
    secure_fs.yetenek_sembolleri()
    pfd, p0 = secure_fs.ac_cikti_ust(cfg)
    rfd = -1
    ctx: Baglam | None = None
    try:
        if secure_fs.var_mi(pfd, cfg.nihai_adi, cfg.dokunulmaz_klasorler):
            raise C1Error(1, "0a", "Nihai klasör zaten var", "yok", cfg.nihai_adi)
        if secure_fs.var_mi(pfd, cfg.gecici_adi, cfg.dokunulmaz_klasorler):
            raise C1Error(1, "0a", "Geçici klasör zaten var", "yok", cfg.gecici_adi)
        deneme = secure_fs.platform_denemesi(pfd, cfg)
        rfd, r0 = secure_fs.r2_olustur(pfd, cfg)
        ctx = Baglam(cfg, pfd, p0, rfd, r0)
        rfd = -1
        pfd = -1
        return _akis(ctx, Politika(cfg), deneme)
    except Exception:
        if ctx is not None:
            try:
                ctx.kapat_hepsi()
            except Exception as kapatma:
                raise C1Error(12, "kapat", "Hata sonrası tanıtıcı kapatılamadı", "kapalı", str(kapatma)) from kapatma
        else:
            if rfd >= 0:
                secure_fs.kapat(rfd)
            if pfd >= 0:
                secure_fs.kapat(pfd)
        raise


def main(argv: list[str] | None = None) -> int:
    ayrıştırıcı = argparse.ArgumentParser(prog="c1", description="C-1 arşivleme ve mühür ayrımı")
    ayrıştırıcı.add_argument("--yapilandirma", required=True)
    ayrıştırıcı.add_argument("--gercek", action="store_true")
    ayrıştırıcı.add_argument("--izole", action="store_true")
    ayrıştırıcı.add_argument("--onay", default="")
    ns = ayrıştırıcı.parse_args(argv)
    try:
        cfg = yukle(ns.yapilandirma, gercek=ns.gercek, onay=ns.onay, izole=ns.izole)
        sonuc = calistir(cfg)
    except C1Error as exc:
        print(exc.satir(), file=sys.stderr)
        return 2
    print(sonuc.ozet, end="" if sonuc.ozet.endswith("\n") else "\n")
    if sonuc.durum == "COMMIT_DURABILITY_UNCERTAIN":
        return 3
    if sonuc.durum in ("DRY-RUN", "TESLIM EDILDI"):
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
