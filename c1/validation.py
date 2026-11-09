"""Metin düzeyinde yol kuralları (YG) ve disk üst sınırı.

Bu modül dosya sistemi çağrısı yapmaz. os.path.normpath yalnız eşitlik içindir.
"""

from __future__ import annotations

import os
import re

from c1.errors import C1Error

_IZIN = re.compile(r"0o[0-7]{3,4}")


def izin_coz(metin: str) -> int:
    metin = metin.strip()
    if not _IZIN.fullmatch(metin):
        raise C1Error(2, "YG", "İzin 0o biçiminde değil", "0o644", metin)
    return int(metin, 8)


def _bilesenler(yol: str) -> list[str]:
    if not yol.startswith("/"):
        raise C1Error(2, "YG", "Yol mutlak değil", "mutlak", yol)
    return yol.split("/")[1:]


def yg_yol(yol: str, kok: str) -> str:
    """YG-1..YG-7 yol kuralları. Arcname döner. Dosya açılmaz."""
    if "\x00" in yol:
        raise C1Error(2, "YG", "Yolda NUL var", "NUL yok", yol)
    if not yol.startswith(kok + "/"):
        raise C1Error(2, "YG", "Yol kaynak kökünün altında değil", kok + "/", yol)
    if yol.endswith("/"):
        raise C1Error(2, "YG", "Yol eğik çizgi ile bitiyor", "bitmez", yol)
    parca = _bilesenler(yol)
    if any(p == "" for p in parca):
        raise C1Error(2, "YG", "Boş yol bileşeni", "boş yok", yol)
    if any(p in (".", "..") for p in parca):
        raise C1Error(2, "YG", "'.' veya '..' bileşeni", "yok", yol)
    if os.path.normpath(yol) != yol:
        raise C1Error(2, "YG", "Yol normalleştirilmemiş", yol, os.path.normpath(yol))
    arc = yol[1:]
    yg_arcname(arc, kok)
    return arc


def yg_arcname(arc: str, kok: str) -> None:
    if "\x00" in arc or arc.startswith("/") or arc.endswith("/") or arc == "":
        raise C1Error(2, "YG", "arcname biçimi geçersiz", "workspace/...", arc)
    on_ek = kok[1:] + "/"
    if not arc.startswith(on_ek):
        raise C1Error(2, "YG", "arcname kaynak öneki ile başlamıyor", on_ek, arc)
    parca = arc.split("/")
    if any(p in ("", ".", "..") for p in parca):
        raise C1Error(2, "YG", "arcname bileşeni geçersiz", "geçerli", arc)


def benzersiz(yollar: list[str], arcnames: list[str]) -> None:
    if len(set(yollar)) != len(yollar):
        raise C1Error(2, "YG", "Yinelenen yol", "benzersiz", "yinelenen")
    if len(set(arcnames)) != len(arcnames):
        raise C1Error(2, "YG", "Yinelenen arcname", "benzersiz", "yinelenen")


def bayt_uzunluk(metin: str) -> int:
    return len(metin.encode("utf-8", "surrogateescape"))


def dizin_kumesi(yollar: list[str]) -> list[str]:
    """İşlem yollarının ata dizinleri. Listeleme yapılmaz; metinden çıkarılır."""
    bulunan: set[str] = set()
    for yol in yollar:
        cur = os.path.dirname(yol)
        while cur and cur not in bulunan:
            bulunan.add(cur)
            if cur == "/":
                break
            yeni = os.path.dirname(cur)
            if yeni == cur:
                break
            cur = yeni
    return sorted(bulunan, key=lambda p: (p.count("/"), p))


def h_ust_sinir(yol_bayt: int, symlink: bool, lk: int) -> int:
    """0c1 başlık üst sınırı. H_i = 512 + X_i."""
    k_i = yol_bayt + 12 + 371 + 512
    if symlink:
        k_i += lk + 16
    x_i = 512 + ((k_i + 511) // 512) * 512
    return 512 + x_i


def tar_grup_boyutu(v_g: int) -> int:
    """T_g = ceil((V_g + 1024) / 10240) * 10240."""
    if v_g < 0:
        raise C1Error(3, "disk", "V_g negatif", ">=0", v_g)
    return ((v_g + 1024 + 10239) // 10240) * 10240


def r_hesabi(n: int, d: int, l_max: int, derinlik_max: int, lk: int, betik: int) -> int:
    """Karttaki R üst sınırı. Taşıma ek alan istemez."""
    p = 2 * l_max + 2
    r = 0
    r += 256 + n * (p + 168) + 2 * lk
    r += 2 * (256 + n * (p + 252) + 2 * lk)
    r += 256 + n * (p + 126)
    r += 2 * (256 + d * (p + 168))
    r += 2 * n * (p + 68)
    r += 3 * 323
    r += 5 * 9 * (p + 300)
    r += 3 * (p + 100)
    r += (derinlik_max + 2) * (p + 200)
    r += 64 * 512
    r += 12 * n * (p + 100)
    r += 8 * d * (p + 100)
    r += 12 * n * (p + 200) + 1000 * 1024
    r += 2000 * (p + 200)
    r += betik
    r += 3 * 4096
    r += 32 * 4096
    return r


def gunluk_butcesi(n: int, l_max: int) -> int:
    p = 2 * l_max + 2
    return 12 * n * (p + 200) + 1000 * 1024


def rapor_butcesi(l_max: int) -> int:
    p = 2 * l_max + 2
    return 2000 * (p + 200)
