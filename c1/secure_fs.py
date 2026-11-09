"""Düşük seviyeli açıklar: openat, O_NOFOLLOW, O_PATH, SYNC_FD, renameat2.

Kaynaklarda yazma, chmod, utime ve bağ çözümü yoktur.
SYNC_FD'ye veri yazılmaz. R1 adı hiç sorgulanmaz.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import stat
from dataclasses import dataclass

from c1.config import Mod, Yapilandirma, yasak_kok_mu
from c1.errors import C1Error, os_hata

O_YOL = os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC
O_ZINCIR = os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
O_NESNE = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
O_OKU = os.O_RDONLY | os.O_NOATIME | os.O_CLOEXEC
O_UST = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
O_YAZ = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
O_SYNC = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC
O_SALT = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
RENAME_NOREPLACE = 1

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libc.renameat2.argtypes = [
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_int,
    ctypes.c_char_p,
    ctypes.c_uint,
]
_libc.renameat2.restype = ctypes.c_int


def oku_arasi(_yol: str) -> None:
    """Okuma tamamlandıktan, son fstat'tan önce. Üretimde boştur."""
    return None


def asama_arasi(_ad: str, _kayitlar: object = None) -> None:
    """Aşamalar arası gözlem. Üretimde boştur."""
    return None


_OZGUN_OKU = oku_arasi
_OZGUN_ASAMA = asama_arasi


def dikisleri_dogrula() -> None:
    if oku_arasi is not _OZGUN_OKU or asama_arasi is not _OZGUN_ASAMA:
        raise C1Error(1, "dikiş", "Gerçek modda gözlem dikişi değişmiş", "özgün", "yama")
    from c1 import commit as commit_mod

    if commit_mod.fsync_cagri is not commit_mod._OZGUN_FSYNC:
        raise C1Error(1, "dikiş", "Gerçek modda fsync dikişi değişmiş", "özgün", "yama")
    if rename_noreplace is not _OZGUN_RENAME:
        raise C1Error(1, "dikiş", "Gerçek modda renameat2 dikişi değişmiş", "özgün", "yama")


@dataclass(frozen=True)
class Meta:
    dev: int
    ino: int
    tur: str
    mod: int
    boyut: int
    uid: int
    gid: int
    atime_ns: int
    mtime_ns: int
    ctime_ns: int

    def kimlik(self) -> tuple[int, int]:
        return (self.dev, self.ino)

    def dis_ata(self) -> tuple[object, ...]:
        return (self.dev, self.ino, self.tur, self.mod)


def meta_metin(m: Meta) -> str:
    return (
        f"dev={m.dev} ino={m.ino} tur={m.tur} mod={m.mod:04o} boyut={m.boyut} "
        f"uid={m.uid} gid={m.gid} atime_ns={m.atime_ns} mtime_ns={m.mtime_ns} ctime_ns={m.ctime_ns}"
    )


def _tur(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "normal"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "dizin"
    raise C1Error(4, "tür", "Desteklenmeyen dosya türü", "normal|symlink|dizin", oct(mode))


def meta_stat(st: os.stat_result) -> Meta:
    return Meta(
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        tur=_tur(st.st_mode),
        mod=stat.S_IMODE(st.st_mode),
        boyut=int(st.st_size),
        uid=int(st.st_uid),
        gid=int(st.st_gid),
        atime_ns=int(st.st_atime_ns),
        mtime_ns=int(st.st_mtime_ns),
        ctime_ns=int(st.st_ctime_ns),
    )


def ayni_yontem(a: Meta, b: Meta) -> None:
    if a != b:
        raise C1Error(4, "M1", "İki ölçüm yöntemi uyuşmuyor", meta_metin(a), meta_metin(b))


def referans_uyum(gorulen: Meta, kayit: Meta, *, tam: bool, kosul: int, asama: str) -> None:
    if tam:
        esit = gorulen == kayit
    else:
        esit = gorulen.dis_ata() == kayit.dis_ata()
    if not esit:
        raise C1Error(kosul, asama, "Metadata kaydıyla uyuşmuyor", meta_metin(kayit), meta_metin(gorulen))


class Politika:
    def __init__(self, cfg: Yapilandirma) -> None:
        self.cfg = cfg

    def dokunulmaz_mi(self, yol: str) -> bool:
        for yasak in self.cfg.dokunulmaz:
            if yol == yasak or yol.startswith(yasak + "/"):
                return True
        return False

    def denetle(self, yol: str) -> None:
        if self.dokunulmaz_mi(yol):
            raise C1Error(2, "kapsam", "Dokunulmaz yola erişim engellendi", "erişim yok", yol)
        if yasak_kok_mu(yol) and self.cfg.mod is not Mod.GERCEK:
            raise C1Error(1, "kapsam", "Yasak kök bu modda açılmaz", "açılmadı", yol)
        if not self.cfg.izinli_mi(yol):
            raise C1Error(1, "kapsam", "Yol izinli kökün dışında", "kök içi", yol)


@dataclass
class SyncKaydi:
    ad: str
    fd: int
    dev: int
    ino: int
    arsiv: bool = False


def yetenek_sembolleri() -> None:
    eksik = [
        ad
        for ad, var in (
            ("O_NOFOLLOW", hasattr(os, "O_NOFOLLOW")),
            ("O_NOATIME", hasattr(os, "O_NOATIME")),
            ("O_PATH", hasattr(os, "O_PATH")),
            ("O_DIRECTORY", hasattr(os, "O_DIRECTORY")),
            ("O_CLOEXEC", hasattr(os, "O_CLOEXEC")),
        )
        if not var
    ]
    if eksik:
        raise C1Error(1, "0a", "Platform bayrağı eksik", "Linux bayrakları", ",".join(eksik))
    if not hasattr(_libc, "renameat2"):
        raise C1Error(1, "0a", "renameat2 yok", "renameat2", "yok")


def rename_noreplace(eski_fd: int, eski: str, yeni_fd: int, yeni: str) -> None:
    for ad in (eski, yeni):
        if not ad or "/" in ad or ad in (".", "..") or "\x00" in ad:
            raise C1Error(12, "K3", "renameat2 adı geçersiz", "tek bileşen", ad)
    ctypes.set_errno(0)
    rc = _libc.renameat2(eski_fd, os.fsencode(eski), yeni_fd, os.fsencode(yeni), RENAME_NOREPLACE)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err) if err else "renameat2", yeni)


_OZGUN_RENAME = rename_noreplace


def kapat(fd: int) -> None:
    if fd < 0:
        return
    try:
        os.close(fd)
    except OSError as exc:
        raise os_hata(12, "kapat", "Tanıtıcı kapatılamadı", "0", exc) from exc


def _tek_ad(ad: str) -> None:
    if not ad or "/" in ad or ad in (".", "..") or "\x00" in ad:
        raise C1Error(12, "çıktı", "Çıktı adı geçersiz", "tek bileşen", ad)


def var_mi(pfd: int, ad: str, dokunulmaz_adlar: tuple[str, ...]) -> bool:
    _tek_ad(ad)
    if ad in dokunulmaz_adlar:
        raise C1Error(1, "dokunulmaz", "Önceki geçersiz klasör sorgulanmaz ve açılmaz", "sorgulanmaz", ad)
    try:
        os.stat(ad, dir_fd=pfd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise os_hata(1, "0a", "Çıktı adı denetlenemedi", "yok ya da var", exc) from exc
    return True


def _karsilastir_yol(
    full: str,
    gorulen: Meta,
    referans: dict[str, Meta] | None,
    kok: str,
    kosul_dizin: int,
) -> None:
    if not referans or full not in referans:
        return
    tam = full == kok or full.startswith(kok + "/")
    referans_uyum(gorulen, referans[full], tam=tam, kosul=kosul_dizin, asama="G1")


def dizin_ac(
    yol: str,
    politika: Politika,
    referans: dict[str, Meta] | None,
    kosul_dizin: int,
    zincir: list[tuple[str, Meta]] | None = None,
) -> tuple[int, Meta]:
    """Dizini O_PATH zinciriyle açar. Dönüş tanıtıcısını çağıran kapatır."""
    if politika.dokunulmaz_mi(yol):
        raise C1Error(2, "kapsam", "Dokunulmaz dizine erişim", "erişim yok", yol)
    if yol != "/" and (politika.cfg.izinli_mi(yol) or yol.startswith(politika.cfg.kaynak_kok + "/") or yol == politika.cfg.kaynak_kok or yol.startswith(politika.cfg.cikti_ust + "/") or yol == politika.cfg.cikti_ust):
        if politika.cfg.mod is not Mod.GERCEK and yasak_kok_mu(yol):
            raise C1Error(1, "kapsam", "Yasak kök açılmaz", "açılmadı", yol)
    kok = politika.cfg.kaynak_kok
    parca = [] if yol == "/" else yol.strip("/").split("/")
    fd = os.open("/", O_YOL)
    try:
        if not parca:
            st = os.fstat(fd)
            meta = meta_stat(st)
            if meta.tur != "dizin":
                raise C1Error(4, "G1", "Kök dizin değil", "dizin", meta.tur)
            _karsilastir_yol("/", meta, referans, kok, kosul_dizin)
            if zincir is not None:
                zincir.append(("/", meta))
            sahip = fd
            fd = -1
            return sahip, meta
        biriken: list[str] = []
        for ad in parca:
            if ad in ("", ".", ".."):
                raise C1Error(8, "G1", "Zincir bileşeni geçersiz", "geçerli", ad)
            biriken.append(ad)
            full = "/" + "/".join(biriken)
            try:
                nxt = os.open(ad, O_ZINCIR, dir_fd=fd)
            except OSError as exc:
                raise C1Error(
                    8,
                    "G1",
                    "Dizin zinciri açılamadı",
                    "dizin",
                    f"{full} errno={exc.errno} {exc.strerror}",
                ) from exc
            try:
                st1 = os.fstat(nxt)
                st2 = os.stat(ad, dir_fd=fd, follow_symlinks=False)
                m1 = meta_stat(st1)
                m2 = meta_stat(st2)
                ayni_yontem(m1, m2)
                if m1.tur != "dizin":
                    raise C1Error(4, "G1", "Zincir bileşeni dizin değil", "dizin", f"{full} {m1.tur}")
                _karsilastir_yol(full, m1, referans, kok, kosul_dizin)
                if zincir is not None:
                    zincir.append((full, m1))
            except Exception:
                kapat(nxt)
                raise
            kapat(fd)
            fd = nxt
            son = m1
        sahip = fd
        fd = -1
        return sahip, son
    finally:
        if fd >= 0:
            kapat(fd)


def ac_cikti_ust(cfg: Yapilandirma) -> tuple[int, tuple[int, int]]:
    politika = Politika(cfg)
    politika.denetle(cfg.cikti_ust)
    fd, meta = dizin_ac(cfg.cikti_ust, politika, None, 8)
    pfd = -1
    try:
        # PFD salt okunur dizin tanıtıcısıdır; O_PATH fsync ve mkdirat için kullanılmaz.
        kapat(fd)
        fd = -1
        pfd = _ac_ust_salt(cfg.cikti_ust, politika)
        st = os.fstat(pfd)
        if not stat.S_ISDIR(st.st_mode):
            raise C1Error(1, "0a", "Çıktı üstü dizin değil", "dizin", cfg.cikti_ust)
        if (int(st.st_dev), int(st.st_ino)) != meta.kimlik():
            raise C1Error(1, "0a", "Çıktı üstü kimliği değişti", meta_metin(meta), f"{st.st_dev}:{st.st_ino}")
        sahip = pfd
        pfd = -1
        return sahip, (int(st.st_dev), int(st.st_ino))
    except Exception:
        if fd >= 0:
            kapat(fd)
        if pfd >= 0:
            kapat(pfd)
        raise


def _ac_ust_salt(yol: str, politika: Politika) -> int:
    parca = yol.strip("/").split("/")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for ad in parca:
            try:
                nxt = os.open(ad, O_UST, dir_fd=fd)
            except OSError as exc:
                raise C1Error(1, "0a", "Çıktı üstü zinciri açılamadı", yol, f"{ad} {exc.strerror}") from exc
            kapat(fd)
            fd = nxt
        sahip = fd
        fd = -1
        return sahip
    finally:
        if fd >= 0:
            kapat(fd)


def platform_denemesi(pfd: int, cfg: Yapilandirma) -> str:
    """En fazla bir deneme dizini ve üç deneme dosyası. Yalnız bunlar silinir."""
    d1 = f"C1_PLATFORM_DENEME_D_{os.getpid()}"
    d2 = f"C1_PLATFORM_DENEME_D2_{os.getpid()}"
    yasak = set(cfg.dokunulmaz_klasorler) | {cfg.gecici_adi, cfg.nihai_adi}
    if d1 in yasak or d2 in yasak:
        raise C1Error(1, "0a", "Platform deneme adı kart adıyla çakışıyor", "ayrı ad", d1)
    eski = os.umask(0o077)
    try:
        try:
            os.mkdir(d1, 0o700, dir_fd=pfd)
        except OSError as exc:
            raise os_hata(1, "0a", "Platform deneme dizini kurulamadı", d1, exc) from exc
        try:
            rename_noreplace(pfd, d1, pfd, d2)
        except OSError as exc:
            _sil_ad(pfd, d1, dizin=True)
            raise C1Error(1, "0a", "renameat2 RENAME_NOREPLACE desteklenmiyor", "0", f"errno={exc.errno}") from exc
        _sil_ad(pfd, d2, dizin=True)
        for i in range(3):
            ad = f"C1_PLATFORM_DENEME_F{i}_{os.getpid()}"
            if ad in yasak:
                raise C1Error(1, "0a", "Platform deneme dosyası kart adıyla çakışıyor", "ayrı ad", ad)
            try:
                fd = os.open(ad, O_YAZ, 0o600, dir_fd=pfd)
            except OSError as exc:
                raise os_hata(1, "0a", "Platform deneme dosyası açılamadı", ad, exc) from exc
            kapat(fd)
            _sil_ad(pfd, ad, dizin=False)
    finally:
        os.umask(eski)
    return "renameat2 RENAME_NOREPLACE: TAMAM; deneme dizini ve 3 dosya silindi"


def _sil_ad(pfd: int, ad: str, *, dizin: bool) -> None:
    if not ad.startswith("C1_PLATFORM_DENEME_"):
        raise C1Error(1, "0a", "Platform denemesi dışında silme yok", "deneme adı", ad)
    try:
        if dizin:
            os.rmdir(ad, dir_fd=pfd)
        else:
            os.unlink(ad, dir_fd=pfd)
    except OSError as exc:
        raise os_hata(1, "0a", "Platform denemesi temizlenemedi", ad, exc) from exc


def r2_olustur(pfd: int, cfg: Yapilandirma) -> tuple[int, tuple[int, int]]:
    if cfg.gecici_adi in cfg.dokunulmaz_klasorler:
        raise C1Error(1, "dokunulmaz", "Geçici ad dokunulmaz listede", "yeni ad", cfg.gecici_adi)
    eski = os.umask(0o077)
    try:
        try:
            os.mkdir(cfg.gecici_adi, 0o700, dir_fd=pfd)
        except OSError as exc:
            raise os_hata(1, "0a", "Geçici klasör oluşturulamadı", "yeni dizin", exc) from exc
    finally:
        os.umask(eski)
    try:
        rfd = os.open(cfg.gecici_adi, O_UST, dir_fd=pfd)
    except OSError as exc:
        raise os_hata(1, "0a", "R2 açılamadı", "dizin tanıtıcısı", exc) from exc
    st = os.fstat(rfd)
    ust = os.fstat(pfd)
    mod = stat.S_IMODE(st.st_mode)
    if not stat.S_ISDIR(st.st_mode):
        kapat(rfd)
        raise C1Error(1, "0a", "Geçici klasör dizin değil", "dizin", cfg.gecici_adi)
    if mod != 0o700:
        kapat(rfd)
        raise C1Error(1, "0a", "R2 izni 0700 değil", "0700", oct(mod))
    if st.st_uid != os.geteuid():
        kapat(rfd)
        raise C1Error(1, "0a", "R2 sahibi euid değil", str(os.geteuid()), str(st.st_uid))
    if st.st_nlink != 2:
        kapat(rfd)
        raise C1Error(1, "0a", "R2 nlink 2 değil", "2", str(st.st_nlink))
    if st.st_dev != ust.st_dev:
        kapat(rfd)
        raise C1Error(1, "0a", "R2 farklı dosya sisteminde", str(ust.st_dev), str(st.st_dev))
    return rfd, (int(st.st_dev), int(st.st_ino))


def ac_cikti_cift(rfd: int, ad: str, kayitlar: list[SyncKaydi], *, arsiv: bool = False) -> tuple[int, SyncKaydi]:
    _tek_ad(ad)
    try:
        wfd = os.open(ad, O_YAZ, 0o600, dir_fd=rfd)
    except OSError as exc:
        raise os_hata(12, "çıktı", "Çıktı dosyası O_EXCL ile açılamadı", ad, exc) from exc
    try:
        sfd = os.open(ad, O_SYNC, dir_fd=rfd)
    except OSError as exc:
        kapat(wfd)
        raise os_hata(12, "SYNC_FD", "SYNC_FD açılamadı", ad, exc) from exc
    try:
        st_w = os.fstat(wfd)
        st_s = os.fstat(sfd)
        st_a = os.stat(ad, dir_fd=rfd, follow_symlinks=False)
    except OSError as exc:
        kapat(wfd)
        kapat(sfd)
        raise os_hata(12, "SYNC_FD", "SYNC_FD kimliği okunamadı", ad, exc) from exc
    ayni = st_w.st_dev == st_s.st_dev == st_a.st_dev and st_w.st_ino == st_s.st_ino == st_a.st_ino
    if not ayni or not stat.S_ISREG(st_w.st_mode) or st_w.st_nlink != 1:
        bek = f"{st_w.st_dev}:{st_w.st_ino}"
        ger = f"sync={st_s.st_dev}:{st_s.st_ino} at={st_a.st_dev}:{st_a.st_ino} nlink={st_w.st_nlink}"
        kapat(wfd)
        kapat(sfd)
        raise C1Error(12, "SYNC_FD", "SYNC_FD inode uyuşmazlığı", bek, ger)
    kayit = SyncKaydi(ad=ad, fd=sfd, dev=int(st_s.st_dev), ino=int(st_s.st_ino), arsiv=arsiv)
    kayitlar.append(kayit)
    return wfd, kayit


def yaz_tampon(wfd: int, veri: bytes) -> None:
    gorunum = memoryview(veri)
    while gorunum:
        try:
            n = os.write(wfd, gorunum)
        except OSError as exc:
            raise os_hata(12, "yazma", "Çıktı yazılamadı", str(len(veri)), exc) from exc
        if n <= 0:
            raise C1Error(12, "yazma", "Çıktı yazımı ilerlemedi", ">0", str(n))
        gorunum = gorunum[n:]


def yaz_dosya(rfd: int, ad: str, veri: bytes, kayitlar: list[SyncKaydi]) -> SyncKaydi:
    wfd, kayit = ac_cikti_cift(rfd, ad, kayitlar)
    try:
        yaz_tampon(wfd, veri)
    finally:
        kapat(wfd)
    return kayit


def oku_cikti(rfd: int, ad: str, kayit: SyncKaydi) -> bytes:
    try:
        fd = os.open(ad, O_SALT, dir_fd=rfd)
    except OSError as exc:
        raise os_hata(12, "okuma-çıktı", "Çıktı salt okunur açılamadı", ad, exc) from exc
    try:
        st = os.fstat(fd)
        if (int(st.st_dev), int(st.st_ino)) != (kayit.dev, kayit.ino):
            raise C1Error(12, "çıktı", "Çıktı inode'u SYNC_FD ile uyuşmuyor", f"{kayit.dev}:{kayit.ino}", f"{st.st_dev}:{st.st_ino}")
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise C1Error(12, "çıktı", "Çıktı normal dosya değil", "normal nlink=1", oct(st.st_mode))
        parca: list[bytes] = []
        while True:
            buf = os.read(fd, 1024 * 1024)
            if not buf:
                break
            parca.append(buf)
        return b"".join(parca)
    finally:
        kapat(fd)


def fchmod_arsiv(kayit: SyncKaydi) -> None:
    try:
        os.fchmod(kayit.fd, 0o444)
    except OSError as exc:
        raise os_hata(12, "izin", "Arşiv 0444 yapılamadı", "0444", exc) from exc


def bos_alan(pfd: int) -> int:
    try:
        st = os.fstatvfs(pfd)
    except OSError as exc:
        raise os_hata(3, "disk", "statvfs başarısız", "boş alan", exc) from exc
    if st.f_frsize <= 0:
        raise C1Error(3, "disk", "f_frsize geçersiz", ">0", st.f_frsize)
    return int(st.f_bavail) * int(st.f_frsize)


def _dosya_iki(dfd: int, ad: str) -> tuple[int, Meta]:
    try:
        g2 = os.open(ad, O_NESNE, dir_fd=dfd)
    except OSError as exc:
        raise C1Error(9, "G2", "Nesne açılamadı", ad, f"errno={exc.errno} {exc.strerror}") from exc
    try:
        st1 = os.fstat(g2)
        st2 = os.stat(ad, dir_fd=dfd, follow_symlinks=False)
        m1 = meta_stat(st1)
        m2 = meta_stat(st2)
        ayni_yontem(m1, m2)
        if m1.tur not in ("normal", "symlink"):
            raise C1Error(4, "G2", "Desteklenmeyen tür", "normal|symlink", m1.tur)
        return g2, m1
    except Exception:
        kapat(g2)
        raise


def meta_dosya(
    yol: str,
    politika: Politika,
    referans_dizin: dict[str, Meta] | None,
    referans_dosya: Meta | None,
    kosul_dizin: int,
    kosul_dosya: int,
) -> Meta:
    politika.denetle(yol)
    dfd, _ = dizin_ac(os.path.dirname(yol), politika, referans_dizin, kosul_dizin)
    try:
        g2, meta = _dosya_iki(dfd, os.path.basename(yol))
        try:
            if referans_dosya is not None:
                referans_uyum(meta, referans_dosya, tam=True, kosul=kosul_dosya, asama="M2")
            return meta
        finally:
            kapat(g2)
    finally:
        kapat(dfd)


@dataclass
class Icerik:
    fd: int
    meta: Meta
    yol: str
    boyut: int

    def kapat(self) -> None:
        if self.fd >= 0:
            kapat(self.fd)
            self.fd = -1


def icerik_ac(
    yol: str,
    politika: Politika,
    referans_dizin: dict[str, Meta] | None,
    referans_dosya: Meta | None,
    kosul_dizin: int,
    kosul_dosya: int,
    zincir: list[tuple[str, Meta]] | None = None,
) -> Icerik:
    """Normal dosyayı G3a ile açar. Symlink burada açılmaz."""
    politika.denetle(yol)
    dfd, _ = dizin_ac(os.path.dirname(yol), politika, referans_dizin, kosul_dizin, zincir)
    g2 = -1
    g3 = -1
    try:
        g2, meta = _dosya_iki(dfd, os.path.basename(yol))
        if meta.tur != "normal":
            raise C1Error(4, "G3a", "İçerik yalnız normal dosyada açılır", "normal", meta.tur)
        if referans_dosya is not None:
            referans_uyum(meta, referans_dosya, tam=True, kosul=kosul_dosya, asama="M2")
        try:
            g3 = os.open(f"/proc/self/fd/{g2}", O_OKU)
        except OSError as exc:
            raise C1Error(5, "G3a", "O_NOATIME açılışı başarısız", "açık", f"errno={exc.errno} {exc.strerror}") from exc
        st3 = os.fstat(g3)
        if (int(st3.st_dev), int(st3.st_ino)) != meta.kimlik() or not stat.S_ISREG(st3.st_mode):
            raise C1Error(9, "G3a", "G3a fstat G2 ile uyuşmuyor", meta_metin(meta), f"{st3.st_dev}:{st3.st_ino}")
        if int(st3.st_size) != meta.boyut or int(st3.st_mtime_ns) != meta.mtime_ns:
            raise C1Error(11, "G3a", "Açılışta boyut veya mtime değişti", meta_metin(meta), f"boyut={st3.st_size}")
        sahip = g3
        g3 = -1
        return Icerik(fd=sahip, meta=meta, yol=yol, boyut=meta.boyut)
    finally:
        if g3 >= 0:
            kapat(g3)
        if g2 >= 0:
            kapat(g2)
        kapat(dfd)


def hash_oku(icerik: Icerik) -> str:
    """Tam okuma. oku_arasi son fstat'tan önce çağrılır."""
    import hashlib

    h = hashlib.sha256()
    kalan = icerik.boyut
    while kalan:
        buf = os.read(icerik.fd, min(1024 * 1024, kalan))
        if not buf:
            raise C1Error(11, "okuma", "Kısa okuma", str(icerik.boyut), str(icerik.boyut - kalan))
        h.update(buf)
        kalan -= len(buf)
    if os.read(icerik.fd, 1):
        raise C1Error(11, "okuma", "Boyuttan fazla bayt", str(icerik.boyut), "daha uzun")
    oku_arasi(icerik.yol)
    st = os.fstat(icerik.fd)
    if int(st.st_size) != icerik.boyut or int(st.st_mtime_ns) != icerik.meta.mtime_ns:
        raise C1Error(
            11,
            "okuma",
            "Okuma sırasında boyut veya mtime değişti",
            f"boyut={icerik.boyut} mtime_ns={icerik.meta.mtime_ns}",
            f"boyut={st.st_size} mtime_ns={st.st_mtime_ns}",
        )
    if (int(st.st_dev), int(st.st_ino)) != icerik.meta.kimlik():
        raise C1Error(9, "okuma", "Okuma sırasında kimlik değişti", meta_metin(icerik.meta), f"{st.st_dev}:{st.st_ino}")
    return h.hexdigest()


def bayt_oku(icerik: Icerik) -> bytes:
    """Envanter ve manifest gibi küçük dosyalar. Hash ile aynı durdurma kuralları."""
    parca: list[bytes] = []
    kalan = icerik.boyut
    while kalan:
        buf = os.read(icerik.fd, min(1024 * 1024, kalan))
        if not buf:
            raise C1Error(11, "okuma", "Kısa okuma", str(icerik.boyut), str(icerik.boyut - kalan))
        parca.append(buf)
        kalan -= len(buf)
        if sum(map(len, parca)) > 32 * 1024 * 1024:
            raise C1Error(2, "okuma", "Beklenenden büyük metin dosyası", "<=32MiB", ">32MiB")
    if os.read(icerik.fd, 1):
        raise C1Error(11, "okuma", "Boyuttan fazla bayt", str(icerik.boyut), "daha uzun")
    oku_arasi(icerik.yol)
    st = os.fstat(icerik.fd)
    if int(st.st_size) != icerik.boyut or int(st.st_mtime_ns) != icerik.meta.mtime_ns:
        raise C1Error(11, "okuma", "Okuma sırasında boyut veya mtime değişti", str(icerik.boyut), str(st.st_size))
    if (int(st.st_dev), int(st.st_ino)) != icerik.meta.kimlik():
        raise C1Error(9, "okuma", "Okuma sırasında kimlik değişti", meta_metin(icerik.meta), f"{st.st_dev}:{st.st_ino}")
    veri = b"".join(parca)
    return veri


class Akis:
    """TarFile'a aktarılan kaynak akışı. Yalnız planlanan boyutu okur."""

    def __init__(self, icerik: Icerik) -> None:
        import hashlib

        self.icerik = icerik
        self.kalan = icerik.boyut
        self._h = hashlib.sha256()

    def read(self, n: int = -1) -> bytes:
        if self.kalan <= 0:
            return b""
        if n is None or n < 0 or n > self.kalan:
            n = self.kalan
        alinan = 0
        parca: list[bytes] = []
        while alinan < n:
            buf = os.read(self.icerik.fd, n - alinan)
            if not buf:
                raise C1Error(11, "okuma", "Akış kısa kaldı", str(self.icerik.boyut), str(self.icerik.boyut - self.kalan))
            parca.append(buf)
            alinan += len(buf)
        veri = b"".join(parca)
        self.kalan -= len(veri)
        self._h.update(veri)
        return veri

    def ozet(self) -> str:
        if self.kalan != 0:
            raise C1Error(11, "okuma", "Akış tamamlanmadı", "0 kalan", str(self.kalan))
        if os.read(self.icerik.fd, 1):
            raise C1Error(11, "okuma", "Akıştan sonra ek bayt", str(self.icerik.boyut), "daha uzun")
        return self._h.hexdigest()

    def son_kontrol(self, beklenen_ozet: str) -> None:
        oku_arasi(self.icerik.yol)
        st = os.fstat(self.icerik.fd)
        if int(st.st_size) != self.icerik.boyut or int(st.st_mtime_ns) != self.icerik.meta.mtime_ns:
            raise C1Error(11, "okuma", "Arşiv okuması sırasında metadata değişti", str(self.icerik.boyut), str(st.st_size))
        if (int(st.st_dev), int(st.st_ino)) != self.icerik.meta.kimlik():
            raise C1Error(9, "okuma", "Arşiv okuması sırasında kimlik değişti", meta_metin(self.icerik.meta), f"{st.st_dev}:{st.st_ino}")
        gelen = self.ozet()
        if gelen != beklenen_ozet:
            raise C1Error(14, "arşiv", "Arşive yazılan baytların hash'i kaynak hash'i değil", beklenen_ozet, gelen)
