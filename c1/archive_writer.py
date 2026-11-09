"""Üç TAR arşivi. PAX, göreli ad, fileobj. SYNC_FD'ye veri yazılmaz."""

from __future__ import annotations

import os
import tarfile
from dataclasses import dataclass, field

from c1.errors import C1Error, os_hata
from c1.inventory import Islem
from c1.secure_fs import Akis, Politika, SyncKaydi, ac_cikti_cift, icerik_ac, oku_cikti
from c1.validation import tar_grup_boyutu

AYAR = (tarfile.PAX_FORMAT, "utf-8", "surrogateescape")
PAX_ANAHTARLARI = (
    "HYPERGROK.orig_mtime_ns",
    "HYPERGROK.orig_atime_ns",
    "HYPERGROK.orig_ctime_ns",
    "HYPERGROK.orig_inode",
    "HYPERGROK.orig_dev",
    "HYPERGROK.grup",
    "HYPERGROK.sha256",
)


@dataclass
class ArsivUye:
    arcname: str
    tur: str
    sha256: str
    linkname: str
    boyut: int
    baslik: bytes
    pax: dict[str, str]
    grup: str


@dataclass
class BellekUye:
    """Bellek içi sınama üyesi. Kaynak dizini açmaz."""

    arcname: str
    tur: str
    mode: int
    uid: int
    gid: int
    boyut: int
    mtime_ns: int
    atime_ns: int
    ctime_ns: int
    ino: int
    dev: int
    grup: str
    sha256: str
    linkname: str = ""
    icerik: bytes = b""
    baslik: bytes = b""
    pax: dict[str, str] = field(default_factory=dict)


def pax_sozluk(
    *,
    mtime_ns: int,
    atime_ns: int,
    ctime_ns: int,
    ino: int,
    dev: int,
    grup: str,
    sha256: str,
) -> dict[str, str]:
    return {
        "HYPERGROK.orig_mtime_ns": str(mtime_ns),
        "HYPERGROK.orig_atime_ns": str(atime_ns),
        "HYPERGROK.orig_ctime_ns": str(ctime_ns),
        "HYPERGROK.orig_inode": str(ino),
        "HYPERGROK.orig_dev": str(dev),
        "HYPERGROK.grup": grup,
        "HYPERGROK.sha256": sha256,
    }


def _tarinfo_kur(
    arcname: str,
    tur: str,
    mode: int,
    uid: int,
    gid: int,
    boyut: int,
    mtime_ns: int,
    linkname: str,
    pax: dict[str, str],
) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=arcname)
    info.type = tarfile.SYMTYPE if tur == "symlink" else tarfile.REGTYPE
    info.mode = mode & 0o7777
    info.uid = uid
    info.gid = gid
    info.uname = ""
    info.gname = ""
    info.size = 0 if tur == "symlink" else boyut
    info.mtime = mtime_ns // 1_000_000_000
    info.linkname = linkname if tur == "symlink" else ""
    info.devmajor = 0
    info.devminor = 0
    info.pax_headers = dict(pax)
    return info


def uye_tarinfo(islem: Islem, sha256: str) -> tarfile.TarInfo:
    if islem.meta is None:
        raise C1Error(12, "tar", "Üye metadatası yok", islem.yol, "yok")
    if len(sha256) != 64:
        raise C1Error(14, "tar", "SHA-256 uzunluğu", "64", str(len(sha256)))
    pax = pax_sozluk(
        mtime_ns=islem.meta.mtime_ns,
        atime_ns=islem.meta.atime_ns,
        ctime_ns=islem.meta.ctime_ns,
        ino=islem.meta.ino,
        dev=islem.meta.dev,
        grup=islem.grup,
        sha256=sha256,
    )
    return _tarinfo_kur(
        islem.arcname,
        islem.tur,
        islem.meta.mod,
        islem.meta.uid,
        islem.meta.gid,
        islem.meta.boyut,
        islem.meta.mtime_ns,
        islem.symlink_metin,
        pax,
    )


def olc_h(islem: Islem) -> int:
    """0c2. Hash alanı 64 sıfırdır; gerçek hash ile aynı uzunluktadır."""
    return len(uye_tarinfo(islem, "0" * 64).tobuf(*AYAR))


def _kapat_tf(tf: tarfile.TarFile, fobj: object) -> None:
    try:
        tf.close()
    except OSError as exc:
        raise os_hata(12, "tar", "TarFile kapanışı başarısız", "kapalı", exc) from exc
    if not tf.closed:
        raise C1Error(12, "tar", "TarFile kapanmadı", True, False)
    try:
        fobj.close()
    except OSError as exc:
        raise os_hata(12, "tar", "Dosya nesnesi kapanışı başarısız", "kapalı", exc) from exc
    if not fobj.closed:
        raise C1Error(12, "tar", "Dosya nesnesi kapanmadı", True, False)


def _ekle_ve_kontrol(tf: tarfile.TarFile, info: tarfile.TarInfo, akis: Akis | None, h_i: int) -> bytes:
    buf = info.tobuf(*AYAR)
    if h_i and len(buf) != h_i:
        raise C1Error(12, "tar", "Başlık uzunluğu H_i değil", str(h_i), str(len(buf)))
    once = tf.offset
    if akis is None:
        tf.addfile(info)
    else:
        tf.addfile(info, akis)
    pad = 0 if info.size == 0 else ((info.size + 511) // 512) * 512
    artis = tf.offset - once
    if artis != len(buf) + pad:
        raise C1Error(12, "tar", "Ofset artışı beklenenden farklı", str(len(buf) + pad), str(artis))
    return buf


def _sonlandirma(veri: bytes, vg: int) -> None:
    beklenen = tar_grup_boyutu(vg)
    if len(veri) != beklenen:
        raise C1Error(12, "tar", "RECORDSIZE yuvarlaması tutmuyor", str(beklenen), str(len(veri)))
    if len(veri) < vg:
        raise C1Error(12, "tar", "Arşiv V_g değerinden kısa", str(vg), str(len(veri)))
    kuyruk = veri[vg:]
    if len(kuyruk) < 1024:
        raise C1Error(12, "tar", "Sonlandırma bloğu 1024 bayttan kısa", ">=1024", str(len(kuyruk)))
    if kuyruk != b"\x00" * len(kuyruk):
        raise C1Error(12, "tar", "Sonlandırma bölgesi sıfır değil", "sıfır", "dolu")


def yaz_arsiv(
    rfd: int,
    ad: str,
    islemler: list[Islem],
    politika: Politika,
    dizinler: dict,
    kayitlar: list[SyncKaydi],
) -> tuple[bytes, list[ArsivUye], SyncKaydi]:
    wfd, sync = ac_cikti_cift(rfd, ad, kayitlar, arsiv=True)
    fobj = os.fdopen(wfd, "wb", closefd=True)
    tf: tarfile.TarFile | None = None
    uyeler: list[ArsivUye] = []
    try:
        tf = tarfile.TarFile(
            name=ad,
            mode="x",
            fileobj=fobj,
            format=AYAR[0],
            encoding=AYAR[1],
            errors=AYAR[2],
            pax_headers={},
        )
        if (tf.format, tf.encoding, tf.errors) != AYAR:
            raise C1Error(12, "tar", "TarFile AYAR ile açılmadı", str(AYAR), f"{tf.format},{tf.encoding},{tf.errors}")
        for islem in islemler:
            if not islem.sha1 or islem.meta is None:
                raise C1Error(14, "tar", "Üyenin kaynak hash'i yok", islem.arcname, islem.sha1)
            info = uye_tarinfo(islem, islem.sha1)
            if islem.tur == "symlink":
                buf = _ekle_ve_kontrol(tf, info, None, islem.h_i)
            else:
                icerik = icerik_ac(islem.yol, politika, dizinler, islem.meta, 17, 16)
                akis = Akis(icerik)
                try:
                    buf = _ekle_ve_kontrol(tf, info, akis, islem.h_i)
                    akis.son_kontrol(islem.sha1)
                finally:
                    icerik.kapat()
            islem.baslik = buf
            islem.pax = dict(info.pax_headers)
            uyeler.append(
                ArsivUye(
                    arcname=islem.arcname,
                    tur=islem.tur,
                    sha256=islem.sha1,
                    linkname=islem.symlink_metin if islem.tur == "symlink" else "",
                    boyut=0 if islem.tur == "symlink" else islem.meta.boyut,
                    baslik=buf,
                    pax=dict(info.pax_headers),
                    grup=islem.grup,
                )
            )
        vg = tf.offset
        _kapat_tf(tf, fobj)
        tf = None
    except Exception:
        if tf is not None and not tf.closed:
            try:
                tf.close()
            except Exception as exc:
                kapanis = ""
                if not fobj.closed:
                    try:
                        fobj.close()
                    except Exception as kapatma:
                        kapanis = f"; dosya nesnesi de kapanmadı: {kapatma}"
                raise C1Error(12, "tar", "TarFile hata sonrası kapanmadı" + kapanis, "kapalı", str(exc)) from exc
        if not fobj.closed:
            try:
                fobj.close()
            except Exception as exc:
                raise C1Error(12, "tar", "Dosya nesnesi hata sonrası kapanmadı", "kapalı", str(exc)) from exc
        raise
    veri = oku_cikti(rfd, ad, sync)
    _sonlandirma(veri, vg)
    return veri, uyeler, sync


def yaz_bellek(uyeler: list[BellekUye]) -> bytes:
    """Sınama için bellek arşivi. Kaynak veya çıktı yolu açmaz."""
    bio_sinif = __import__("io").BytesIO
    fobj = bio_sinif()
    tf = tarfile.TarFile(
        name="bellek.tar",
        mode="x",
        fileobj=fobj,
        format=AYAR[0],
        encoding=AYAR[1],
        errors=AYAR[2],
        pax_headers={},
    )
    for uye in uyeler:
        pax = pax_sozluk(
            mtime_ns=uye.mtime_ns,
            atime_ns=uye.atime_ns,
            ctime_ns=uye.ctime_ns,
            ino=uye.ino,
            dev=uye.dev,
            grup=uye.grup,
            sha256=uye.sha256,
        )
        info = _tarinfo_kur(
            uye.arcname,
            uye.tur,
            uye.mode,
            uye.uid,
            uye.gid,
            uye.boyut,
            uye.mtime_ns,
            uye.linkname,
            pax,
        )
        akis = None
        if uye.tur != "symlink":
            akis = bio_sinif(uye.icerik)
        buf = info.tobuf(*AYAR)
        if akis is None:
            tf.addfile(info)
        else:
            tf.addfile(info, akis)
        uye.baslik = buf
        uye.pax = dict(pax)
    vg = tf.offset
    tf.close()
    veri = fobj.getvalue()
    _sonlandirma(veri, vg)
    return veri
