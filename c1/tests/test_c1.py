"""C-1 sentetik sınamaları. Gerçek /workspace ve /home/box açılmaz."""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import platform
from contextlib import redirect_stdout
import re
import stat
import tarfile
import tempfile
import unittest

from c1 import archive_validator, archive_writer, commit, secure_fs
from c1.archive_writer import ArsivUye, BellekUye
from c1.config import (
    DISK_YEDEK_BAYT,
    GERCEK_CIKTI_UST,
    GERCEK_ENVANTER,
    GERCEK_KAYNAK_KOK,
    GERCEK_R5_DIZIN,
    MANIFEST_ADI,
    MANIFEST_BOYUT,
    MANIFEST_SHA256,
    MK_ADLARI,
    ONAY_METIN,
    NIHAI_ADI,
    PYTHON_GERCEK,
    R1_ADI,
    R2_ADI,
    Mk,
    Mod,
    Yapilandirma,
    yukle,
)
from c1.errors import C1Error
from c1.main import calistir, main
from c1.tests.destek import Dosya, MK5_GOVDE_EK, _temizle, hazirla, kur_gercek_duzen

GERCEK_MK5 = "/home/box/" + MK5_GOVDE_EK

KOK_BELLEK = "/tmp/c1bellek"
ARC_KOK = "tmp/c1bellek/"


def _uye(ad: str, icerik: bytes, ino: int = 10) -> BellekUye:
    return BellekUye(
        arcname=ARC_KOK + ad,
        tur="normal",
        mode=0o644,
        uid=1,
        gid=1,
        boyut=len(icerik),
        mtime_ns=1_700_000_000_000_000_000,
        atime_ns=1_700_000_000_000_000_001,
        ctime_ns=1_700_000_000_000_000_002,
        ino=ino,
        dev=50,
        grup="A",
        sha256=hashlib.sha256(icerik).hexdigest(),
        icerik=icerik,
    )


def _oku(yol: str, ikili: bool = False):
    if ikili:
        with open(yol, "rb") as fh:
            return fh.read()
    with open(yol, encoding="utf-8") as fh:
        return fh.read()


def _cevir(uye: BellekUye) -> ArsivUye:
    return ArsivUye(
        arcname=uye.arcname,
        tur=uye.tur,
        sha256=uye.sha256,
        linkname=uye.linkname,
        boyut=uye.boyut,
        baslik=uye.baslik,
        pax=dict(uye.pax),
        grup=uye.grup,
    )


class C1Testleri(unittest.TestCase):
    def setUp(self) -> None:
        self._oku = secure_fs.oku_arasi
        self._asama = secure_fs.asama_arasi
        self._fsync = commit.fsync_cagri
        self._rename = secure_fs.rename_noreplace
        self._close = tarfile.TarFile.close
        self._k5 = commit.k5
        self._open = os.open
        self._ac = secure_fs.ac_cikti_ust

    def tearDown(self) -> None:
        secure_fs.oku_arasi = self._oku
        secure_fs.asama_arasi = self._asama
        commit.fsync_cagri = self._fsync
        secure_fs.rename_noreplace = self._rename
        tarfile.TarFile.close = self._close
        commit.k5 = self._k5
        os.open = self._open
        secure_fs.ac_cikti_ust = self._ac

    def _sahne(self, **kw):
        kok = tempfile.mkdtemp(prefix="c1t_")
        self.addCleanup(_temizle, kok)
        return hazirla(kok, **kw)

    def _basari(self, sahne, sonuc) -> None:
        self.assertEqual(sonuc.durum, "TESLIM EDILDI", sonuc.ozet)
        self.assertIsNone(sonuc.k5_hata)
        self.assertTrue(os.path.isdir(sahne.nihai()))
        self.assertFalse(os.path.exists(sahne.r2()))
        rapor = _oku(os.path.join(sahne.nihai(), "RAPOR.txt"))
        bildirim = _oku(os.path.join(sahne.nihai(), "TESLIM_BILDIRIMI.txt"))
        self.assertIn("Kapanış: henüz yapılmadı", rapor)
        self.assertIn("fazla dosya kontrolü yapılmadı", rapor)
        self.assertIn("manifest bayt özgünlüğü doğrulanamadı", rapor)
        self.assertIn("YG: GEÇTİ", rapor)
        self.assertIn("TESLIM EDILDI", bildirim)
        self.assertNotIn("TESLIM EDILDI", rapor)
        for ad in ("A_arastirma.tar", "B1_karantina.tar", "B2_karantina.tar"):
            yol = os.path.join(sahne.nihai(), ad)
            self.assertTrue(os.path.isfile(yol), ad)
            self.assertEqual(stat.S_IMODE(os.lstat(yol).st_mode), 0o444)

    def _dur(self, sahne, kosul: int) -> C1Error:
        with self.assertRaises(C1Error) as cm:
            calistir(sahne.cfg)
        self.assertEqual(cm.exception.kosul, kosul, cm.exception)
        self.assertFalse(os.path.isdir(sahne.nihai()))
        return cm.exception

    def test_01_normal_dosya(self) -> None:
        sahne = self._sahne()
        once = os.lstat(sahne.payload).st_mtime_ns
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        self.assertEqual(os.lstat(sahne.payload).st_mtime_ns, once)
        self.assertEqual(_oku(sahne.payload, True), b"merhaba")
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            adlar = tf.getnames()
            self.assertIn(sahne.payload[1:], adlar)
            uye = tf.getmember(sahne.payload[1:])
            self.assertTrue(uye.isreg())
            self.assertEqual(tf.extractfile(uye).read(), b"merhaba")
            self.assertEqual(uye.pax_headers["HYPERGROK.sha256"], hashlib.sha256(b"merhaba").hexdigest())
            self.assertEqual(uye.pax_headers["HYPERGROK.grup"], "A")
        with tarfile.open(os.path.join(sahne.nihai(), "B1_karantina.tar"), "r") as tf:
            self.assertEqual(tf.getmembers(), [])

    def test_02_symlink(self) -> None:
        metin = "hedef-dolayli"
        sahne = self._sahne(dosyalar=[Dosya("bag", b"", "A", "symlink", 0o777, metin)])

        def yasak(*_a, **_k):
            raise AssertionError("bağ metni okundu")

        eski = os.readlink
        os.readlink = yasak
        try:
            sonuc = calistir(sahne.cfg)
        finally:
            os.readlink = eski
        self._basari(sahne, sonuc)
        rapor = _oku(os.path.join(sahne.nihai(), "RAPOR.txt"))
        self.assertIn("DOLAYLI DOĞRULANDI", rapor)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            uye = tf.getmember(sahne.payload[1:])
            self.assertTrue(uye.issym())
            self.assertEqual(uye.linkname, metin)
            self.assertEqual(uye.size, 0)
        kaynak = _oku(os.path.join(sahne.nihai(), "A_kaynak_1.sha256"))
        self.assertIn("DOLAYLI", kaynak)
        self.assertIn(hashlib.sha256(metin.encode()).hexdigest(), kaynak)

    def test_03_bos_dosya(self) -> None:
        sahne = self._sahne(dosyalar=[Dosya("bos.dat", b"")])
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            uye = tf.getmember(sahne.payload[1:])
            self.assertEqual(uye.size, 0)
            self.assertEqual(tf.extractfile(uye).read(), b"")

    def test_04_buyuk_dosya(self) -> None:
        veri = b"A" * 200_000
        sahne = self._sahne(dosyalar=[Dosya("buyuk.bin", veri)])
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            uye = tf.getmember(sahne.payload[1:])
            self.assertEqual(hashlib.sha256(tf.extractfile(uye).read()).hexdigest(), hashlib.sha256(veri).hexdigest())

    def test_05_unicode_ad(self) -> None:
        sahne = self._sahne(dosyalar=[Dosya("αβγ_文件.txt", b"unicode")])
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            self.assertIn(sahne.payload[1:], tf.getnames())

    def test_06_turkce_ad(self) -> None:
        sahne = self._sahne(dosyalar=[Dosya("ölçü_şığ.txt", "çiğ".encode())])
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            uye = tf.getmember(sahne.payload[1:])
            self.assertEqual(tf.extractfile(uye).read(), "çiğ".encode())

    def test_07_uzun_ad(self) -> None:
        sahne = self._sahne(dosyalar=[Dosya("u" * 150 + ".txt", b"uzun")])
        sonuc = calistir(sahne.cfg)
        self._basari(sahne, sonuc)
        self.assertGreater(len(sahne.payload[1:]), 150)

    def test_08_yinelenen_arcname(self) -> None:
        sahne = self._sahne(yinelenen=True)
        self._dur(sahne, 2)

    def test_09_path_traversal(self) -> None:
        sahne = self._sahne(traversal=True)
        self._dur(sahne, 2)
        self.assertEqual(_oku(sahne.disari, True), b"GIZLI-TRAVERSAL\n")

    def test_10_symlink_kacis(self) -> None:
        sahne = self._sahne(kacis=True)
        self._dur(sahne, 8)
        self.assertEqual(_oku(sahne.disari, True), b"GIZLI-DISARI\n")

    def test_11_kaynak_degisir(self) -> None:
        sahne = self._sahne()

        def kanca(yol: str) -> None:
            if yol == sahne.payload:
                fd = os.open(yol, os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC)
                try:
                    os.write(fd, b"X")
                finally:
                    os.close(fd)

        secure_fs.oku_arasi = kanca
        self._dur(sahne, 11)

    def test_12_metadata_degisir(self) -> None:
        sahne = self._sahne()

        def kanca(ad: str) -> None:
            if ad == "adim1-oncesi":
                os.utime(sahne.payload, ns=(10, 20))

        secure_fs.asama_arasi = kanca
        self._dur(sahne, 7)

    def test_13_yanlis_hash(self) -> None:
        sahne = self._sahne(dosyalar=[Dosya("veri/not.txt", b"merhaba", sha256="ab" * 32)])
        self._dur(sahne, 14)

    def test_14_bozuk_manifest(self) -> None:
        sahne = self._sahne(manifest="bozuk")
        self._dur(sahne, 6)

    def test_15_eksik_manifest_satiri(self) -> None:
        sahne = self._sahne(manifest="eksik")
        self._dur(sahne, 6)

    def test_16_fazla_manifest_satiri(self) -> None:
        sahne = self._sahne(manifest="fazla")
        self._dur(sahne, 6)

    def test_17_mk5_ve_a_ek_dokunulmaz(self) -> None:
        sahne = self._sahne(a_ek=True)
        self.assertIsNotNone(sahne.a_ek)
        once_mk5 = os.lstat(sahne.mk5)
        once_ek = os.lstat(sahne.a_ek)
        mk5_icerik = _oku(sahne.mk5, True)
        ek_icerik = _oku(sahne.a_ek, True)
        yasaklar = {sahne.mk5, os.path.dirname(sahne.mk5), sahne.a_ek, os.path.dirname(sahne.a_ek)}
        orijinaller = {
            "open": os.open,
            "stat": os.stat,
            "lstat": os.lstat,
            "listdir": os.listdir,
            "scandir": os.scandir,
            "readlink": os.readlink,
            "bopen": builtins.open,
        }

        def ihlal(op: str, yol: str) -> None:
            if yol in yasaklar or any(yol.startswith(k + os.sep) or yol.startswith(k + "/") for k in yasaklar):
                raise AssertionError(f"{op} dokunulmaz yola değdi: {yol}")

        def adaylar(path, kwargs) -> list[str]:
            bulunan = []
            if isinstance(path, (str, bytes)):
                bulunan.append(os.fsdecode(path))
            dfd = kwargs.get("dir_fd")
            if isinstance(dfd, int) and dfd >= 0 and isinstance(path, (str, bytes)):
                try:
                    temel = orijinaller["readlink"](f"/proc/self/fd/{dfd}")
                except OSError:
                    temel = ""
                if temel:
                    bulunan.append(os.path.join(temel, os.fsdecode(path)))
            return bulunan

        def sarmala(op, fn):
            def ic(*a, **k):
                yol = a[0] if a else k.get("path", "")
                for aday in adaylar(yol, k):
                    ihlal(op, aday)
                return fn(*a, **k)

            return ic

        os.open = sarmala("open", orijinaller["open"])
        os.stat = sarmala("stat", orijinaller["stat"])
        os.lstat = sarmala("lstat", orijinaller["lstat"])
        os.listdir = sarmala("listdir", orijinaller["listdir"])
        os.scandir = sarmala("scandir", orijinaller["scandir"])
        os.readlink = sarmala("readlink", orijinaller["readlink"])
        builtins.open = sarmala("builtins.open", orijinaller["bopen"])
        try:
            sonuc = calistir(sahne.cfg)
        finally:
            os.open = orijinaller["open"]
            os.stat = orijinaller["stat"]
            os.lstat = orijinaller["lstat"]
            os.listdir = orijinaller["listdir"]
            os.scandir = orijinaller["scandir"]
            os.readlink = orijinaller["readlink"]
            builtins.open = orijinaller["bopen"]
        self._basari(sahne, sonuc)
        self.assertEqual(_oku(sahne.mk5, True), mk5_icerik)
        self.assertEqual(_oku(sahne.a_ek, True), ek_icerik)
        sonra_mk5 = os.lstat(sahne.mk5)
        sonra_ek = os.lstat(sahne.a_ek)
        self.assertEqual((once_mk5.st_dev, once_mk5.st_ino, once_mk5.st_mtime_ns), (sonra_mk5.st_dev, sonra_mk5.st_ino, sonra_mk5.st_mtime_ns))
        self.assertEqual((once_ek.st_dev, once_ek.st_ino, once_ek.st_mtime_ns), (sonra_ek.st_dev, sonra_ek.st_ino, sonra_ek.st_mtime_ns))
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            self.assertNotIn(sahne.a_ek[1:], tf.getnames())
            self.assertNotIn(sahne.mk5[1:], tf.getnames())

    def test_18_sync_fd_inode(self) -> None:
        sahne = self._sahne()
        gercek = os.open

        def sarmal(path, flags, *a, **k):
            fd = gercek(path, flags, *a, **k)
            if path == "PLATFORM_KONTROL.txt" and (flags & os.O_CREAT) and (flags & os.O_EXCL):
                dfd = k["dir_fd"]
                os.unlink(path, dir_fd=dfd)
                yeni = gercek(path, flags, *a, **k)
                os.close(yeni)
            return fd

        os.open = sarmal
        hata = self._dur(sahne, 12)
        self.assertIn("SYNC_FD", hata.asama)

    def test_19_r2_var(self) -> None:
        sahne = self._sahne()
        os.mkdir(sahne.r2(), 0o700)
        self._dur(sahne, 1)
        self.assertTrue(os.path.isdir(sahne.r2()))

    def test_20_nihai_var(self) -> None:
        sahne = self._sahne()
        os.mkdir(sahne.nihai(), 0o700)
        with self.assertRaises(C1Error) as cm:
            calistir(sahne.cfg)
        self.assertEqual(cm.exception.kosul, 1)
        self.assertFalse(os.path.exists(sahne.r2()))
        self.assertTrue(os.path.isdir(sahne.nihai()))

    def test_21_rename_basarisiz(self) -> None:
        sahne = self._sahne()
        orijinal = secure_fs.rename_noreplace

        def sarmal(eski_fd, eski, yeni_fd, yeni):
            if eski == sahne.cfg.r2_adi:
                raise OSError(17, "File exists")
            return orijinal(eski_fd, eski, yeni_fd, yeni)

        secure_fs.rename_noreplace = sarmal
        self._dur(sahne, 12)
        self.assertTrue(os.path.isdir(sahne.r2()))

    def test_22_fsync_basarisiz(self) -> None:
        sahne = self._sahne()

        def patlat(_fd: int, _rol: str) -> None:
            raise OSError(5, "fsync")

        commit.fsync_cagri = patlat
        self._dur(sahne, 12)
        self.assertTrue(os.path.isdir(sahne.r2()))
        self.assertFalse(os.path.exists(sahne.nihai()))

    def test_23_tar_kapanis(self) -> None:
        sahne = self._sahne()

        def patlat(self_tf):
            raise OSError(5, "kapanış")

        tarfile.TarFile.close = patlat
        self._dur(sahne, 12)
        self.assertFalse(os.path.exists(sahne.nihai()))

    def test_24_eksik_uye(self) -> None:
        bir = _uye("a.txt", b"bir")
        iki = _uye("b.txt", b"iki", ino=11)
        veri = archive_writer.yaz_bellek([bir])
        with self.assertRaises(C1Error) as cm:
            archive_validator.dogrula_tampon(veri, [_cevir(bir), _cevir(iki)], KOK_BELLEK, set())
        self.assertEqual(cm.exception.kosul, 13)
        self.assertIn("eksik", cm.exception.aciklama)

    def test_25_fazla_uye(self) -> None:
        bir = _uye("a.txt", b"bir")
        iki = _uye("b.txt", b"iki", ino=11)
        veri = archive_writer.yaz_bellek([bir, iki])
        with self.assertRaises(C1Error) as cm:
            archive_validator.dogrula_tampon(veri, [_cevir(bir)], KOK_BELLEK, set())
        self.assertEqual(cm.exception.kosul, 13)
        self.assertIn("fazla", cm.exception.aciklama)

    def test_26_pax_uyusmazligi(self) -> None:
        bir = _uye("a.txt", b"pax")
        veri = archive_writer.yaz_bellek([bir])
        beklenen = _cevir(bir)
        beklenen.pax["HYPERGROK.orig_inode"] = "999999"
        with self.assertRaises(C1Error) as cm:
            archive_validator.dogrula_tampon(veri, [beklenen], KOK_BELLEK, set())
        self.assertEqual(cm.exception.kosul, 15)

    def test_27_k5_hatasi_durumu_degistirmez(self) -> None:
        sahne = self._sahne()

        def patlat(*_a, **_k):
            raise OSError(5, "k5")

        commit.k5 = patlat
        sonuc = calistir(sahne.cfg)
        self.assertEqual(sonuc.durum, "TESLIM EDILDI")
        self.assertIsNotNone(sonuc.k5_hata)
        self.assertTrue(os.path.isdir(sahne.nihai()))
        self.assertFalse(os.path.exists(os.path.join(sahne.nihai(), "TESLIM_BILDIRIMI.txt")))

    def test_28_r1_acilmaz(self) -> None:
        sahne = self._sahne()
        r1 = os.path.join(sahne.cikti, R1_ADI)
        os.mkdir(r1, 0o700)
        iz = os.path.join(r1, "iz.txt")
        with open(iz, "wb") as fh:
            fh.write(b"KORU")
        once = os.lstat(r1)
        once_dosya = os.lstat(iz)
        gorulen: list[str] = []
        gercek_open = os.open
        gercek_stat = os.stat

        def open_sarmal(path, flags, *a, **k):
            if path == R1_ADI or (isinstance(path, str) and path.rstrip("/").endswith("/" + R1_ADI)):
                raise AssertionError(f"R1 açıldı: {path}")
            gorulen.append(os.fsdecode(path) if isinstance(path, (str, bytes)) else str(path))
            return gercek_open(path, flags, *a, **k)

        def stat_sarmal(path, *a, **k):
            if path == R1_ADI:
                raise AssertionError("R1 stat")
            return gercek_stat(path, *a, **k)

        os.open = open_sarmal
        os.stat = stat_sarmal
        try:
            sonuc = calistir(sahne.cfg)
        finally:
            os.open = gercek_open
            os.stat = gercek_stat
        self._basari(sahne, sonuc)
        self.assertEqual(_oku(iz, True), b"KORU")
        self.assertEqual((once.st_dev, once.st_ino), (os.lstat(r1).st_dev, os.lstat(r1).st_ino))
        self.assertEqual(once_dosya.st_mtime_ns, os.lstat(iz).st_mtime_ns)
        self.assertNotIn(R1_ADI, gorulen)

    def test_29_dry_run_kaynak_acmaz(self) -> None:
        acilan: list[str] = []
        gercek = os.open

        def sarmal(path, flags, *a, **k):
            if isinstance(path, (str, bytes)):
                acilan.append(os.fsdecode(path))
            return gercek(path, flags, *a, **k)

        os.open = sarmal
        tampon = io.StringIO()
        try:
            with redirect_stdout(tampon):
                kod = main(["--yapilandirma", "c1/ornek_yapilandirma.json"])
        finally:
            os.open = gercek
        self.assertEqual(kod, 0)
        self.assertIn("DRY-RUN", tampon.getvalue())
        for yol in acilan:
            self.assertFalse(yol == "/workspace" or yol.startswith("/workspace/") or yol == "/home/box" or yol.startswith("/home/box/"))

    def test_30_onaysiz_gercek_mod_acilmaz(self) -> None:
        gercek = os.open
        cagri = {"n": 0}

        def sarmal(path, flags, *a, **k):
            cagri["n"] += 1
            return gercek(path, flags, *a, **k)

        os.open = sarmal
        try:
            with self.assertRaises(C1Error) as cm:
                yukle("/tmp/c1-olmayan-yapilandirma.json", gercek=True, onay="hayir", izole=False)
        finally:
            os.open = gercek
        self.assertEqual(cm.exception.kosul, 1)
        self.assertEqual(cagri["n"], 0)
        self.assertIn("ONAY C-1", str(cm.exception.beklenen))

    def test_31_gercek_mod_surum_kapisi(self) -> None:
        mk = {
            anahtar: Mk(anahtar, GERCEK_R5_DIZIN + "/" + MK_ADLARI[anahtar], "0" * 64)
            for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4")
        }
        mk["MK-5"] = Mk("MK-5", GERCEK_MK5, None)
        cfg = Yapilandirma(
            mod=Mod.GERCEK,
            onay="ONAY C-1",
            kaynak_kok=GERCEK_KAYNAK_KOK,
            envanter_yolu=GERCEK_ENVANTER,
            cikti_ust=GERCEK_CIKTI_UST,
            r1_adi=R1_ADI,
            r2_adi=R2_ADI,
            nihai_adi=NIHAI_ADI,
            r5_dizin=GERCEK_R5_DIZIN,
            manifest_adi=MANIFEST_ADI,
            mk=mk,
            kapsam_sabitleri=True,
            manifest_sabitleri_zorunlu=True,
            disk_yedek_bayt=DISK_YEDEK_BAYT,
        )

        def patlat(*_a, **_k):
            raise AssertionError("gerçek kök açıldı")

        secure_fs.ac_cikti_ust = patlat
        if platform.python_version() != PYTHON_GERCEK:
            with self.assertRaises(C1Error) as cm:
                calistir(cfg)
            self.assertEqual(cm.exception.kosul, 1)
            self.assertIn(PYTHON_GERCEK, str(cm.exception.beklenen))
        else:
            self.skipTest("Bu ortam kart sürümünde; gerçek kök açılmadan sürüm kapısı sınanamaz")

    def test_32_k4_belirsiz(self) -> None:
        sahne = self._sahne()
        orijinal = commit.fsync_cagri

        def secici(fd: int, rol: str) -> None:
            if rol == "ust":
                raise OSError(5, "fsync")
            orijinal(fd, rol)

        commit.fsync_cagri = secici
        sonuc = calistir(sahne.cfg)
        self.assertEqual(sonuc.durum, "COMMIT_DURABILITY_UNCERTAIN")
        self.assertTrue(os.path.isdir(sahne.nihai()))
        self.assertFalse(os.path.exists(sahne.r2()))
        bildirim = _oku(os.path.join(sahne.nihai(), "TESLIM_BILDIRIMI.txt"))
        self.assertIn("COMMIT_DURABILITY_UNCERTAIN", bildirim)
        self.assertNotIn("durum: TESLIM EDILDI", bildirim)

    def test_33_manifest_sabiti_boyut(self) -> None:
        sahne = self._sahne(manifest_sabit=True)
        hata = self._dur(sahne, 6)
        self.assertEqual(hata.beklenen, str(MANIFEST_BOYUT))
        self.assertEqual(MANIFEST_SHA256, "a98b9dc8c7742f9588da23e6a670d7f5f138407953d1a7a835b27a1cfaf5ca02")

    def test_34_statik_yasaklar(self) -> None:
        kok = os.path.join(os.path.dirname(__file__), "..")
        yasak_hex = re.compile(r"\b[0-9a-f]{64}\b")
        for ad in os.listdir(kok):
            if not ad.endswith(".py"):
                continue
            yol = os.path.join(kok, ad)
            metin = _oku(yol)
            self.assertNotIn("import pathlib", metin, ad)
            self.assertNotIn("subprocess", metin, ad)
            self.assertNotIn("os.readlink", metin, ad)
            self.assertNotIn("readlinkat", metin, ad)
            bulunan = set(yasak_hex.findall(metin))
            fazla = bulunan - {MANIFEST_SHA256}
            self.assertEqual(fazla, set(), ad)
            if ad != "config.py":
                self.assertNotIn('"/workspace"', metin, ad)
                self.assertNotIn('"/home/box"', metin, ad)


class SyscallKalkan:
    """open/stat/mkdir ve dir_fd birleşimini yasak köklere karşı izler."""

    def __init__(self, kokler: list[str], bilesenler: set[str]) -> None:
        self.kokler = kokler
        self.bilesenler = bilesenler
        self._eski: dict[str, object] = {}

    def __enter__(self) -> "SyscallKalkan":
        import builtins

        self._eski = {
            "open": os.open,
            "stat": os.stat,
            "lstat": os.lstat,
            "listdir": os.listdir,
            "scandir": os.scandir,
            "readlink": os.readlink,
            "mkdir": os.mkdir,
            "unlink": os.unlink,
            "rmdir": os.rmdir,
            "chmod": os.chmod,
            "access": os.access,
            "bopen": builtins.open,
            "rename": secure_fs.rename_noreplace,
        }
        for ad in ("open", "stat", "lstat", "listdir", "scandir", "readlink", "mkdir", "unlink", "rmdir", "chmod", "access"):
            setattr(os, ad, self._sar(ad, self._eski[ad]))
        builtins.open = self._sar("builtins.open", self._eski["bopen"])
        secure_fs.rename_noreplace = self._rename_sar()
        return self

    def __exit__(self, *_exc) -> None:
        import builtins

        for ad, fn in self._eski.items():
            if ad == "bopen":
                builtins.open = fn
            elif ad == "rename":
                secure_fs.rename_noreplace = fn
            else:
                setattr(os, ad, fn)

    def _ihlal(self, op: str, yol: str) -> None:
        if yol in self.bilesenler:
            raise AssertionError(f"{op} dokunulmaz bileşen: {yol}")
        for kok in self.kokler:
            if yol == kok or yol.startswith(kok + "/"):
                raise AssertionError(f"{op} dokunulmaz yol: {yol}")

    def _adaylar(self, path, kwargs) -> list[str]:
        bulunan = []
        if isinstance(path, (str, bytes)):
            bulunan.append(os.fsdecode(path))
        dfd = kwargs.get("dir_fd")
        if isinstance(dfd, int) and dfd >= 0 and isinstance(path, (str, bytes)):
            try:
                temel = self._eski["readlink"](f"/proc/self/fd/{dfd}")
            except OSError:
                temel = ""
            if temel:
                bulunan.append(os.path.join(temel, os.fsdecode(path)))
        return bulunan

    def _sar(self, op: str, fn):
        def ic(*a, **k):
            yol = a[0] if a else k.get("path", "")
            for aday in self._adaylar(yol, k):
                self._ihlal(op, aday)
            return fn(*a, **k)

        return ic

    def _rename_sar(self):
        def ic(eski_fd, eski, yeni_fd, yeni):
            for ad, dfd in ((eski, eski_fd), (yeni, yeni_fd)):
                self._ihlal("renameat2", ad)
                try:
                    temel = self._eski["readlink"](f"/proc/self/fd/{dfd}")
                except OSError:
                    temel = ""
                if temel:
                    self._ihlal("renameat2", os.path.join(temel, ad))
            return self._eski["rename"](eski_fd, eski, yeni_fd, yeni)

        return ic


class GercekDuzenTestleri(unittest.TestCase):
    def setUp(self) -> None:
        self._ac = secure_fs.ac_cikti_ust

    def tearDown(self) -> None:
        secure_fs.ac_cikti_ust = self._ac

    def _cfg(self, mk5: str) -> Yapilandirma:
        mk = {
            anahtar: Mk(anahtar, GERCEK_R5_DIZIN + "/" + MK_ADLARI[anahtar], "0" * 64)
            for anahtar in ("MK-1", "MK-2", "MK-3", "MK-4")
        }
        mk["MK-5"] = Mk("MK-5", mk5, None)
        return Yapilandirma(
            mod=Mod.GERCEK,
            onay=ONAY_METIN,
            kaynak_kok=GERCEK_KAYNAK_KOK,
            envanter_yolu=GERCEK_ENVANTER,
            cikti_ust=GERCEK_CIKTI_UST,
            r1_adi=R1_ADI,
            r2_adi=R2_ADI,
            nihai_adi=NIHAI_ADI,
            r5_dizin=GERCEK_R5_DIZIN,
            manifest_adi=MANIFEST_ADI,
            mk=mk,
            kapsam_sabitleri=True,
            manifest_sabitleri_zorunlu=True,
            disk_yedek_bayt=DISK_YEDEK_BAYT,
        )

    def test_35_mk5_cikti_ustunde_r1_r2_nihai_disi(self) -> None:
        cfg = self._cfg(GERCEK_MK5)
        self.assertIn(GERCEK_MK5, cfg.dokunulmaz)
        self.assertTrue(GERCEK_MK5.startswith(GERCEK_CIKTI_UST + "/"))
        for ad in (R1_ADI, R2_ADI, NIHAI_ADI):
            with self.assertRaises(C1Error) as cm:
                self._cfg(GERCEK_CIKTI_UST + "/" + ad + "/ek.md")
            self.assertIn("R1, R2 veya nihai", cm.exception.aciklama)
        with self.assertRaises(C1Error) as cm:
            self._cfg(GERCEK_KAYNAK_KOK + "/bot-eki.md")
        self.assertIn("kaynak kökü", cm.exception.aciklama)

        kok = tempfile.mkdtemp(prefix="c1json_")
        self.addCleanup(_temizle, kok)
        json_yol = os.path.join(kok, "var/tmp/c1_r11_yapilandirma/c1_gercek.json")
        os.makedirs(os.path.dirname(json_yol), 0o700)
        govde = {
            "kaynak_kok": GERCEK_KAYNAK_KOK,
            "envanter_yolu": GERCEK_ENVANTER,
            "cikti_ust": GERCEK_CIKTI_UST,
            "r1_adi": R1_ADI,
            "r2_adi": R2_ADI,
            "nihai_adi": NIHAI_ADI,
            "r5_dizin": GERCEK_R5_DIZIN,
            "manifest_adi": MANIFEST_ADI,
            "mk": {
                "MK-1": {"sha256": "0" * 64},
                "MK-2": {"sha256": "0" * 64},
                "MK-3": {"sha256": "0" * 64},
                "MK-4": {"sha256": "0" * 64},
                "MK-5": {"yol": GERCEK_MK5},
            },
        }
        with open(json_yol, "w", encoding="utf-8") as fh:
            fh.write(__import__("json").dumps(govde))
        yuklenen = yukle(json_yol, gercek=True, onay=ONAY_METIN, izole=False)
        self.assertTrue(yuklenen.kapsam_sabitleri)
        self.assertTrue(yuklenen.manifest_sabitleri_zorunlu)
        self.assertEqual(yuklenen.disk_yedek_bayt, DISK_YEDEK_BAYT)
        self.assertEqual(yuklenen.envanter_yolu, GERCEK_ENVANTER)
        self.assertEqual(yuklenen.r5_dizin, GERCEK_R5_DIZIN)
        self.assertEqual(yuklenen.mk["MK-5"].yol, GERCEK_MK5)
        govde["kapsam_sabitleri"] = False
        with open(json_yol, "w", encoding="utf-8") as fh:
            fh.write(__import__("json").dumps(govde))
        with self.assertRaises(C1Error) as cm:
            yukle(json_yol, gercek=True, onay=ONAY_METIN, izole=False)
        self.assertIn("kapsam", cm.exception.aciklama)

        def patlat(*_a, **_k):
            raise AssertionError("gerçek kök açıldı")

        secure_fs.ac_cikti_ust = patlat
        if platform.python_version() != PYTHON_GERCEK:
            with self.assertRaises(C1Error) as cm:
                calistir(yuklenen)
            self.assertEqual(cm.exception.kosul, 1)

    def test_36_gercek_duzen_uctan_uca(self) -> None:
        kok = tempfile.mkdtemp(prefix="c1duzen_")
        self.addCleanup(_temizle, kok)
        sahne = kur_gercek_duzen(kok)
        self.assertTrue(sahne.mk5.startswith(sahne.cikti + "/agent-data/"))
        self.assertTrue(sahne.ekstra["json"].endswith("var/tmp/c1_r11_yapilandirma/c1_gercek.json"))
        once_mk5 = os.lstat(sahne.mk5)
        once_agent = os.lstat(sahne.ekstra["agent_data"])
        once_r1 = os.lstat(sahne.ekstra["r1"])
        mk5_icerik = _oku(sahne.mk5, True)
        bilesen = {"agent-data", "attachments", os.path.basename(sahne.mk5)}
        with SyscallKalkan([sahne.ekstra["agent_data"], sahne.ekstra["r1"], sahne.mk5], bilesen):
            sonuc = calistir(sahne.cfg)
        self.assertEqual(sonuc.durum, "TESLIM EDILDI", sonuc.ozet)
        self.assertIsNone(sonuc.k5_hata)
        self.assertEqual(_oku(sahne.mk5, True), mk5_icerik)
        sonra_mk5 = os.lstat(sahne.mk5)
        sonra_agent = os.lstat(sahne.ekstra["agent_data"])
        sonra_r1 = os.lstat(sahne.ekstra["r1"])
        self.assertEqual((once_mk5.st_dev, once_mk5.st_ino, once_mk5.st_mtime_ns), (sonra_mk5.st_dev, sonra_mk5.st_ino, sonra_mk5.st_mtime_ns))
        self.assertEqual((once_agent.st_dev, once_agent.st_ino, once_agent.st_mtime_ns), (sonra_agent.st_dev, sonra_agent.st_ino, sonra_agent.st_mtime_ns))
        self.assertEqual((once_r1.st_dev, once_r1.st_ino), (sonra_r1.st_dev, sonra_r1.st_ino))
        self.assertEqual(_oku(os.path.join(sahne.ekstra["r1"], "iz.txt"), True), b"KORU")
        rapor = _oku(os.path.join(sahne.nihai(), "R5_FREEZE_HASH.txt"))
        self.assertIn("MK-5 yalnız metinsel yol", rapor)
        self.assertIn(sahne.mk5, rapor)
        with tarfile.open(os.path.join(sahne.nihai(), "A_arastirma.tar"), "r") as tf:
            self.assertNotIn(sahne.mk5[1:], tf.getnames())


if __name__ == "__main__":
    unittest.main()
