"""M1 kayıt ve M2 karşılaştırma. Dizin listesi yapılmaz."""

from __future__ import annotations

import os

from c1.errors import C1Error
from c1.inventory import Islem
from c1.secure_fs import Meta, Politika, icerik_ac, meta_dosya, meta_metin, referans_uyum
from c1.secure_fs import dizin_ac, kapat
from c1.validation import bayt_uzunluk


def sa_kontrol(metin: str, boyut: int) -> None:
    """S-A. Uzunluk güvenli zincirin st_size değerine eşittir; bağ metni okunmaz."""
    gelen = bayt_uzunluk(metin)
    if gelen != boyut:
        raise C1Error(10, "S-A", "Symlink metin uzunluğu st_size ile uyuşmuyor", str(boyut), str(gelen))


def dizinleri_kaydet(yollar: list[str], politika: Politika) -> dict[str, Meta]:
    kayit: dict[str, Meta] = {}
    for yol in yollar:
        _fd, meta = dizin_ac(yol, politika, kayit, 8)
        kapat(_fd)
        if yol in kayit and kayit[yol] != meta:
            raise C1Error(8, "0d", "Dizin kaydı ikinci ölçümde değişti", meta_metin(kayit[yol]), meta_metin(meta))
        kayit[yol] = meta
    return kayit


def dizinleri_karsilastir(yollar: list[str], politika: Politika, kayit: dict[str, Meta], kosul: int) -> None:
    for yol in yollar:
        _fd, meta = dizin_ac(yol, politika, kayit, kosul)
        kapat(_fd)
        tam = yol == politika.cfg.kaynak_kok or yol.startswith(politika.cfg.kaynak_kok + "/")
        referans_uyum(meta, kayit[yol], tam=tam, kosul=kosul, asama="dizin")


def dosya_kaydet(islem: Islem, politika: Politika, dizinler: dict[str, Meta]) -> Meta:
    meta = meta_dosya(islem.yol, politika, dizinler, None, 8, 4)
    if islem.tur == "symlink":
        if meta.tur != "symlink":
            raise C1Error(4, "0e", "Symlink beklenirken tür farklı", "symlink", meta.tur)
        sa_kontrol(islem.symlink_metin, meta.boyut)
    elif meta.tur != "normal":
        raise C1Error(4, "0e", "Normal dosya beklenirken tür farklı", "normal", meta.tur)
    if islem.tur == "normal" and islem.izin == 0o444 and meta.mod != 0o444:
        raise C1Error(6, "0e", "K444 izin sapması", "0444", oct(meta.mod))
    islem.meta = meta
    return meta


def dosyalari_karsilastir(islemler: list[Islem], politika: Politika, dizinler: dict[str, Meta], kosul: int) -> None:
    for islem in islemler:
        if islem.meta is None:
            raise C1Error(kosul, "M2", "Dosya referansı yok", islem.yol, "yok")
        meta = meta_dosya(islem.yol, politika, dizinler, islem.meta, 8, kosul)
        if islem.tur == "symlink":
            sa_kontrol(islem.symlink_metin, meta.boyut)
            if meta.ino != islem.meta.ino or meta.mtime_ns != islem.meta.mtime_ns or meta.ctime_ns != islem.meta.ctime_ns:
                raise C1Error(10, "S-A", "Symlink inode veya zaman değişti", meta_metin(islem.meta), meta_metin(meta))


def noatime_dene(islem: Islem, politika: Politika, dizinler: dict[str, Meta]) -> None:
    if islem.tur == "symlink":
        dosyalari_karsilastir([islem], politika, dizinler, 16)
        return
    icerik = icerik_ac(islem.yol, politika, dizinler, islem.meta, 17, 16)
    try:
        if icerik.meta.tur != "normal":
            raise C1Error(5, "0f", "O_NOATIME normal dosyada değil", "normal", icerik.meta.tur)
    finally:
        icerik.kapat()


def csv_dosya(islemler: list[Islem]) -> str:
    satirlar = ["yol,dev,inode,tur,izin,boyut,uid,gid,atime_ns,mtime_ns,ctime_ns"]
    for islem in islemler:
        m = islem.meta
        if m is None:
            raise C1Error(4, "metadata", "Dosya metadatası yok", islem.yol, "yok")
        satirlar.append(
            f"{_hucre(islem.yol)},{m.dev},{m.ino},{m.tur},{m.mod:04o},{m.boyut},{m.uid},{m.gid},{m.atime_ns},{m.mtime_ns},{m.ctime_ns}"
        )
    return "\n".join(satirlar) + "\n"


def csv_dizin(kayit: dict[str, Meta]) -> str:
    satirlar = ["yol,dev,inode,tur,izin,atime_ns,mtime_ns,ctime_ns"]
    for yol in sorted(kayit):
        m = kayit[yol]
        satirlar.append(
            f"{_hucre(yol)},{m.dev},{m.ino},{m.tur},{m.mod:04o},{m.atime_ns},{m.mtime_ns},{m.ctime_ns}"
        )
    return "\n".join(satirlar) + "\n"


def _hucre(yol: str) -> str:
    if any(k in yol for k in ",\"\n"):
        return '"' + yol.replace('"', '""') + '"'
    return yol


def ebeveyn(yol: str) -> str:
    return os.path.dirname(yol)
