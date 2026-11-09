"""C-1 hata modeli. Hata yutulmaz, düzeltilmez ve yeniden denenmez."""

from __future__ import annotations


class C1Error(Exception):
    """Tek bir durdurma. Otomatik onarım yolu yoktur."""

    def __init__(
        self,
        kosul: int,
        asama: str,
        aciklama: str,
        beklenen: object,
        gercek: object,
    ) -> None:
        self.kosul = int(kosul)
        self.asama = asama
        self.aciklama = aciklama
        self.beklenen = beklenen
        self.gercek = gercek
        self.kod = f"C1-DUR-{self.kosul:02d}"
        super().__init__(
            f"{self.kod} aşama={asama} {aciklama} "
            f"beklenen={beklenen!r} gerçek={gercek!r}"
        )

    def satir(self) -> str:
        return (
            f"{self.kod}\t{self.asama}\t{self.aciklama}\t"
            f"beklenen={self.beklenen}\tgerçek={self.gercek}"
        )


def os_hata(kosul: int, asama: str, aciklama: str, beklenen: object, exc: OSError) -> C1Error:
    errno = getattr(exc, "errno", None)
    return C1Error(
        kosul,
        asama,
        aciklama,
        beklenen,
        f"errno={errno} {exc.strerror}",
    )
