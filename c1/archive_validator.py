"""Arşiv bellekte doğrulanır. Diske üye çıkarılmaz."""

from __future__ import annotations

import hashlib
import io
import tarfile

from c1.archive_writer import AYAR, PAX_ANAHTARLARI, ArsivUye
from c1.errors import C1Error
from c1.validation import yg_arcname


def dogrula_tampon(veri: bytes, beklenen: list[ArsivUye], kok: str, a_ek_yollar: set[str]) -> None:
    a_ek_arc = {yol[1:] for yol in a_ek_yollar if yol.startswith("/")}
    tf = tarfile.TarFile(fileobj=io.BytesIO(veri), mode="r", encoding=AYAR[1], errors=AYAR[2])
    try:
        uyeler = tf.getmembers()
        if len({m.name for m in uyeler}) != len(uyeler):
            raise C1Error(13, "arşiv", "Yinelenen arşiv üyesi", "benzersiz", "yinelenen")
        if len(uyeler) < len(beklenen):
            raise C1Error(13, "arşiv", "Arşivde eksik üye", str(len(beklenen)), str(len(uyeler)))
        if len(uyeler) > len(beklenen):
            raise C1Error(13, "arşiv", "Arşivde fazla üye", str(len(beklenen)), str(len(uyeler)))
        for gelen, uye in zip(uyeler, beklenen):
            if gelen.name in a_ek_arc or (gelen.name.startswith("/") and gelen.name[1:] in a_ek_arc):
                raise C1Error(13, "arşiv", "A-ek arşive girmiş", "yok", gelen.name)
            try:
                yg_arcname(gelen.name, kok)
            except C1Error as exc:
                raise C1Error(13, "arşiv", "Üye adı YG kuralına aykırı", uye.arcname, gelen.name) from exc
            if gelen.name != uye.arcname:
                raise C1Error(13, "arşiv", "Üye adı grup listesiyle uyuşmuyor", uye.arcname, gelen.name)
            if gelen.type not in (tarfile.REGTYPE, tarfile.SYMTYPE):
                raise C1Error(13, "arşiv", "Desteklenmeyen üye türü", "REGTYPE|SYMTYPE", repr(gelen.type))
            if uye.tur == "symlink":
                if not gelen.issym() or gelen.size != 0 or gelen.linkname != uye.linkname:
                    raise C1Error(13, "arşiv", "Symlink üyesi uyuşmuyor", uye.linkname, gelen.linkname)
            else:
                if not gelen.isreg() or gelen.issym():
                    raise C1Error(13, "arşiv", "Normal üye türü uyuşmuyor", "normal", repr(gelen.type))
                akis = tf.extractfile(gelen)
                if akis is None:
                    raise C1Error(13, "arşiv", "Normal üyenin içeriği okunamadı", uye.arcname, "yok")
                ozet = hashlib.sha256(akis.read()).hexdigest()
                if ozet != uye.sha256:
                    raise C1Error(14, "arşiv", "Arşiv içeriği kaynak hash'i değil", uye.sha256, ozet)
            for anahtar in PAX_ANAHTARLARI:
                if gelen.pax_headers.get(anahtar) != uye.pax.get(anahtar):
                    raise C1Error(
                        15,
                        "PAX",
                        f"{anahtar} uyuşmuyor",
                        uye.pax.get(anahtar),
                        gelen.pax_headers.get(anahtar),
                    )
            if gelen.pax_headers.get("HYPERGROK.sha256") != uye.sha256:
                raise C1Error(15, "PAX", "PAX sha256 kaynak hash'i değil", uye.sha256, gelen.pax_headers.get("HYPERGROK.sha256"))
            if uye.baslik:
                if gelen.offset_data < gelen.offset:
                    raise C1Error(15, "PAX", "Başlık aralığı ters", str(gelen.offset), str(gelen.offset_data))
                ham = veri[gelen.offset:gelen.offset_data]
                if ham != uye.baslik:
                    raise C1Error(15, "PAX", "Başlık baytı yazılan başlıkla uyuşmuyor", str(len(uye.baslik)), str(len(ham)))
    finally:
        tf.close()
