"""K1–K5 teslim. K4 başarısızlığı durumu COMMIT_DURABILITY_UNCERTAIN yapar.

K5 hatası bu durumu değiştirmez. Geri alma, silme ve yeniden adlandırma yoktur.
"""

from __future__ import annotations

import os

from c1 import secure_fs
from c1.errors import C1Error, os_hata
from c1.secure_fs import SyncKaydi


def fsync_cagri(fd: int, rol: str) -> None:
    if fd < 0:
        raise C1Error(12, "fsync", "Geçersiz tanıtıcı", "açık", f"{rol}:{fd}")
    os.fsync(fd)


_OZGUN_FSYNC = fsync_cagri


def k1() -> str:
    """os.write tamponu çekirdeğe iner. Açık Python dosya nesnesi bırakılmaz."""
    return "uygulama tamponları boşaltıldı"


def k2(rfd: int, kayitlar: list[SyncKaydi], r0: tuple[int, int]) -> str:
    st_r = os.fstat(rfd)
    if (int(st_r.st_dev), int(st_r.st_ino)) != r0:
        raise C1Error(12, "K2", "R2 kimliği K2 başında R0 değil", str(r0), f"{st_r.st_dev}:{st_r.st_ino}")
    # Alt dizin oluşturulmaz. Liste boşsa en derinden fsync adımı atlanır.
    alt: list[str] = []
    for ad in sorted(alt, key=lambda p: p.count("/"), reverse=True):
        raise C1Error(12, "K2", "Beklenmeyen alt dizin", "yok", ad)
    for kayit in kayitlar:
        if kayit.fd < 0:
            raise C1Error(12, "K2", "SYNC_FD kapalı", kayit.ad, "kapalı")
        st = os.fstat(kayit.fd)
        if (int(st.st_dev), int(st.st_ino)) != (kayit.dev, kayit.ino):
            raise C1Error(12, "K2", "SYNC_FD kimliği değişti", f"{kayit.dev}:{kayit.ino}", f"{st.st_dev}:{st.st_ino}")
        try:
            fsync_cagri(kayit.fd, "dosya")
        except OSError as exc:
            raise os_hata(12, "K2", "Çıktı fsync başarısız", kayit.ad, exc) from exc
    try:
        fsync_cagri(rfd, "r2")
    except OSError as exc:
        raise os_hata(12, "K2", "R2 fsync başarısız", "RFD", exc) from exc
    for kayit in kayitlar:
        secure_fs.kapat(kayit.fd)
        kayit.fd = -1
    st2 = os.fstat(rfd)
    if (int(st2.st_dev), int(st2.st_ino)) != r0:
        raise C1Error(12, "K2", "R2 kimliği fsync sonrası değişti", str(r0), f"{st2.st_dev}:{st2.st_ino}")
    return "dosyalar, alt dizinler ve R2 fsync edildi; SYNC_FD kapatıldı; PFD ve RFD açık"


def k3(pfd: int, rfd: int, r2_adi: str, nihai_adi: str, p0: tuple[int, int], r0: tuple[int, int]) -> str:
    st_p = os.fstat(pfd)
    st_r = os.fstat(rfd)
    if (int(st_p.st_dev), int(st_p.st_ino)) != p0:
        raise C1Error(12, "K3", "PFD kimliği P0 değil", str(p0), f"{st_p.st_dev}:{st_p.st_ino}")
    if (int(st_r.st_dev), int(st_r.st_ino)) != r0:
        raise C1Error(12, "K3", "RFD kimliği R0 değil", str(r0), f"{st_r.st_dev}:{st_r.st_ino}")
    try:
        secure_fs.rename_noreplace(pfd, r2_adi, pfd, nihai_adi)
    except OSError as exc:
        raise os_hata(12, "K3", "renameat2 başarısız", "0", exc) from exc
    st_son = os.fstat(rfd)
    if (int(st_son.st_dev), int(st_son.st_ino)) != r0:
        raise C1Error(12, "K3", "Taşıma sonrası RFD kimliği R0 değil", str(r0), f"{st_son.st_dev}:{st_son.st_ino}")
    return "renameat2 RENAME_NOREPLACE tamam"


def k4(pfd: int, p0: tuple[int, int]) -> str:
    try:
        fsync_cagri(pfd, "ust")
    except OSError:
        return "COMMIT_DURABILITY_UNCERTAIN"
    st = os.fstat(pfd)
    if (int(st.st_dev), int(st.st_ino)) != p0:
        return "COMMIT_DURABILITY_UNCERTAIN"
    return "TESLIM EDILDI"


def k5(ctx: object, metin: str) -> None:
    rfd = ctx.rfd
    pfd = ctx.pfd
    kayit = secure_fs.yaz_dosya(rfd, "TESLIM_BILDIRIMI.txt", metin.encode("utf-8"), ctx.sync)
    st = os.fstat(kayit.fd)
    if (int(st.st_dev), int(st.st_ino)) != (kayit.dev, kayit.ino):
        raise C1Error(12, "K5", "Bildirim SYNC_FD kimliği uyuşmuyor", f"{kayit.dev}:{kayit.ino}", f"{st.st_dev}:{st.st_ino}")
    try:
        fsync_cagri(kayit.fd, "k5")
    except OSError as exc:
        raise os_hata(12, "K5", "Bildirim fsync başarısız", "TESLIM_BILDIRIMI.txt", exc) from exc
    secure_fs.kapat(kayit.fd)
    kayit.fd = -1
    try:
        fsync_cagri(rfd, "r2")
    except OSError as exc:
        raise os_hata(12, "K5", "Nihai dizin fsync başarısız", "RFD", exc) from exc
    secure_fs.kapat(rfd)
    ctx.rfd = -1
    secure_fs.kapat(pfd)
    ctx.pfd = -1
