"""C1 envanterinin güvenli okunması ve işlem listesinin kurulması.

A-ek satırları metin olarak ayrılır; bu modül onlar için sistem çağrısı yapmaz.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from c1.config import (
    A_EK_GRUP,
    A_EK_N,
    ENVANTER_N,
    GRUP_ESLEME,
    GRUP_SAYILARI,
    GRUPLAR,
    ISLEM_N,
    K444_N,
    NORMAL_N,
    SYMLINK_N,
    SYMLINK_ONEK,
    Yapilandirma,
    csv_baslik,
)
from c1.errors import C1Error
from c1.secure_fs import Meta, Politika, bayt_oku, dizin_ac, icerik_ac, kapat, meta_dosya, meta_metin
from c1.validation import benzersiz, izin_coz, yg_yol


@dataclass
class Islem:
    yol: str
    arcname: str
    grup: str
    grup_ham: str
    tur: str
    izin: int
    boyut_envanter: int
    symlink_metin: str
    mtime_trt: str
    bayrak: str
    not_alani: str
    meta: Meta | None = None
    h_i: int = 0
    sha1: str = ""
    baslik: bytes = b""
    pax: dict[str, str] = field(default_factory=dict)


def _ayir(metin: str, cfg: Yapilandirma) -> tuple[list[Islem], list[str]]:
    try:
        reader = csv.DictReader(io.StringIO(metin))
    except csv.Error as exc:
        raise C1Error(2, "0b", "CSV okunamadı", "csv", str(exc)) from exc
    if reader.fieldnames is None or tuple(reader.fieldnames) != csv_baslik():
        raise C1Error(2, "0b", "CSV başlığı kartla uyuşmuyor", ",".join(csv_baslik()), reader.fieldnames)
    islemler: list[Islem] = []
    a_ek: list[str] = []
    mk5 = cfg.mk["MK-5"].yol
    for i, row in enumerate(reader, start=2):
        try:
            yol = row["yol"] or ""
            grup_ham = row["grup"] or ""
            tur_ham = row["tur"] or ""
            izin = izin_coz(row["izin"] or "")
            boyut = int(row["boyut_bayt"])
            mtime_trt = row["mtime_trt"] or ""
            bayrak = row["bayrak"] or ""
            not_alani = row["not"] or ""
        except (TypeError, ValueError, C1Error) as exc:
            raise C1Error(2, "0b", f"Satır {i} çözülemedi", "geçerli satır", str(exc)) from exc
        if yol == mk5:
            raise C1Error(2, "0b", "MK-5 envantere alınamaz", "envanterde yok", yol)
        if grup_ham == A_EK_GRUP:
            a_ek.append(yol)
            continue
        if grup_ham not in GRUP_ESLEME:
            raise C1Error(2, "0b", "Bilinmeyen grup", ",".join((*GRUP_ESLEME, A_EK_GRUP)), grup_ham)
        grup = GRUP_ESLEME[grup_ham]
        if tur_ham == "file":
            tur, metin_link = "normal", ""
        elif tur_ham.startswith(SYMLINK_ONEK):
            tur, metin_link = "symlink", tur_ham[len(SYMLINK_ONEK):]
            if not metin_link:
                raise C1Error(10, "0b", "Symlink hedefi boş", "symlink->hedef", tur_ham)
        else:
            raise C1Error(2, "0b", "Bilinmeyen tür", "file|symlink->hedef", tur_ham)
        if tur == "symlink":
            if grup != "A":
                raise C1Error(10, "0b", "Symlink yalnız A_arastirma grubunda", "A_arastirma", grup_ham)
            if boyut != 0:
                raise C1Error(2, "0b", "Symlink boyut_bayt 0 olmalı", "0", boyut)
        elif boyut < 0:
            raise C1Error(2, "0b", "Negatif boyut", ">=0", boyut)
        arc = yg_yol(yol, cfg.kaynak_kok)
        islemler.append(
            Islem(
                yol=yol,
                arcname=arc,
                grup=grup,
                grup_ham=grup_ham,
                tur=tur,
                izin=izin,
                boyut_envanter=boyut,
                symlink_metin=metin_link,
                mtime_trt=mtime_trt,
                bayrak=bayrak,
                not_alani=not_alani,
            )
        )
    benzersiz([k.yol for k in islemler], [k.arcname for k in islemler])
    if len(set(a_ek)) != len(a_ek):
        raise C1Error(2, "0b", "Yinelenen A-ek yolu", "benzersiz", "yinelenen")
    for yol in a_ek:
        if any(k.yol == yol for k in islemler):
            raise C1Error(2, "0b", "A-ek işlem listesine sızdı", "dışarıda", yol)
    return islemler, a_ek


def sayilari_dogrula(cfg: Yapilandirma, ham_satir: int, islemler: list[Islem], a_ek: list[str]) -> None:
    if not cfg.kapsam_sabitleri:
        return
    if ham_satir != ENVANTER_N:
        raise C1Error(2, "0b", "Envanter sayısı", str(ENVANTER_N), str(ham_satir))
    if len(islemler) != ISLEM_N:
        raise C1Error(2, "0b", "İşlem listesi sayısı", str(ISLEM_N), str(len(islemler)))
    if len(a_ek) != A_EK_N:
        raise C1Error(2, "0b", "A-ek sayısı", str(A_EK_N), str(len(a_ek)))
    for grup, beklenen in GRUP_SAYILARI.items():
        gelen = sum(1 for k in islemler if k.grup == grup)
        if gelen != beklenen:
            raise C1Error(2, "0b", f"Grup {grup} sayısı", str(beklenen), str(gelen))
    normal = sum(1 for k in islemler if k.tur == "normal")
    link = sum(1 for k in islemler if k.tur == "symlink")
    if normal != NORMAL_N or link != SYMLINK_N:
        raise C1Error(2, "0b", "Normal/symlink sayısı", f"{NORMAL_N}/{SYMLINK_N}", f"{normal}/{link}")
    k444 = [k for k in islemler if k.tur == "normal" and k.izin == 0o444]
    if len(k444) != K444_N:
        raise C1Error(2, "0b", "K444 sayısı", str(K444_N), str(len(k444)))
    r5 = set(cfg.r5_yollari())
    if not r5 <= {k.yol for k in k444}:
        raise C1Error(2, "0b", "K444 beş R5 dosyasını içermiyor", "5", "eksik")


def oku(cfg: Yapilandirma, politika: Politika) -> tuple[str, Meta, list[tuple[str, Meta]]]:
    """0b: envanteri bir kez okur; okuma sonrası zinciri ve fstat'ı karşılaştırır."""
    zincir: list[tuple[str, Meta]] = []
    icerik = icerik_ac(cfg.envanter_yolu, politika, None, None, 2, 2, zincir)
    try:
        veri = bayt_oku(icerik)
        meta0 = icerik.meta
    finally:
        icerik.kapat()
    if meta0.tur != "normal":
        raise C1Error(2, "0b", "Envanter normal dosya değil", "normal", meta0.tur)
    zincir2: list[tuple[str, Meta]] = []
    dfd, _ = dizin_ac(cfg.envanter_yolu.rsplit("/", 1)[0], politika, None, 2, zincir2)
    kapat(dfd)
    meta1 = meta_dosya(cfg.envanter_yolu, politika, None, None, 2, 2)
    if meta1 != meta0:
        raise C1Error(2, "0b", "Envanter okuma sonrası fstat değişti", meta_metin(meta0), meta_metin(meta1))
    if [p for p, _ in zincir] != [p for p, _ in zincir2]:
        raise C1Error(2, "0b", "Envanter zincir yolları değişti", [p for p, _ in zincir], [p for p, _ in zincir2])
    for (y1, m1), (y2, m2) in zip(zincir, zincir2):
        if y1 != y2:
            raise C1Error(2, "0b", "Envanter zinciri okuma sonrası değişti", y1, y2)
        tam = y1 == cfg.kaynak_kok or y1.startswith(cfg.kaynak_kok + "/")
        if tam and m1 != m2:
            raise C1Error(2, "0b", "Envanter zinciri okuma sonrası değişti", meta_metin(m1), meta_metin(m2))
        if not tam and m1.dis_ata() != m2.dis_ata():
            raise C1Error(2, "0b", "Envanter ata kimliği değişti", meta_metin(m1), meta_metin(m2))
    try:
        metin = veri.decode("utf-8")
    except UnicodeError as exc:
        raise C1Error(2, "0b", "Envanter UTF-8 değil", "utf-8", str(exc)) from exc
    return metin, meta0, zincir


def coz(metin: str, cfg: Yapilandirma) -> tuple[list[Islem], list[str], int]:
    # Satır sayısı başlık hariç. sayilari_dogrula ham envanter satırını ister.
    govde = metin.splitlines()
    if not govde:
        raise C1Error(2, "0b", "Envanter boş", "başlık + satırlar", "boş")
    islemler, a_ek = _ayir(metin, cfg)
    ham = len(islemler) + len(a_ek)
    sayilari_dogrula(cfg, ham, islemler, a_ek)
    for yol in a_ek:
        cfg.dokunulmaz.add(yol)
    for kayit in cfg.r5_yollari():
        if not any(k.yol == kayit and k.grup == "A" and k.tur == "normal" for k in islemler):
            raise C1Error(6, "0b", "R5 dosyası işlem listesinde Grup A değil", kayit, "yok")
    return islemler, a_ek, ham
