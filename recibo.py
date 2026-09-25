"""Comprovantes do Mini App (opção B, Patrick 25/09): imagem com cara de comprovante do
Nubank (pix) ou de pedido do iFood, postada no chat como mensagem DELE (answerWebAppQuery).
Uso pessoal: marcas reais, logos do Wikimedia Commons (domínio público) em webapp/marcas/.
"""
from __future__ import annotations

import io
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

MARCAS = Path(__file__).parent / "webapp" / "marcas"
W = 720
PAD = 56
NU_PURPLE = (130, 10, 209)
IFOOD_RED = (234, 29, 44)
INK = (31, 31, 31)
GRAY = (112, 112, 112)
LINE = (230, 230, 230)
MESES = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")
BANCO_DELA = ("Itaú Unibanco S.A.", "Personnalité")

_FONT_PATHS = {
    False: ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    True: ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in _FONT_PATHS[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _brl(valor: float) -> str:
    inteiro, cent = f"{valor:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{cent}"


def _data(when: datetime) -> str:
    return f"{when.day:02d} {MESES[when.month - 1]} {when.year} · {when:%H:%M}"


def _logo(name: str, height: int, crop_symbol: bool = False) -> Optional[Image.Image]:
    path = MARCAS / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    if crop_symbol:                      # pix.png = losango + "pix powered by Banco Central"
        img = img.crop((0, 0, img.height, img.height))
        img = img.crop(img.getbbox() or (0, 0, img.width, img.height))
    ratio = height / img.height
    return img.resize((max(1, int(img.width * ratio)), height), Image.LANCZOS)


class _Canvas:
    def __init__(self, accent):
        self.img = Image.new("RGB", (W, 1600), "white")
        self.d = ImageDraw.Draw(self.img)
        self.y = 0
        self.d.rectangle((0, 0, W, 10), fill=accent)
        self.y = 10 + 44

    def paste(self, logo: Optional[Image.Image], x: int = PAD):
        if logo is not None:
            self.img.paste(logo, (x, self.y), logo)
            self.y += logo.height

    def text(self, s: str, size: int, *, bold=False, color=INK, gap=10, x=PAD):
        f = _font(size, bold)
        self.d.text((x, self.y), s, font=f, fill=color)
        self.y += f.getbbox("Ág")[3] + gap

    def rule(self, gap=26):
        self.y += gap
        self.d.line((PAD, self.y, W - PAD, self.y), fill=LINE, width=2)
        self.y += gap

    def field(self, label: str, value: str, *, extra: str = "", icon: Optional[Image.Image] = None):
        self.text(label, 22, color=GRAY, gap=6)
        x = PAD
        if icon is not None:
            self.img.paste(icon, (PAD, self.y + 2), icon)
            x = PAD + icon.width + 10
        for i, line in enumerate(textwrap.wrap(value, 38) or [""]):
            self.text(line, 28, bold=(i == 0 and not extra), gap=4, x=x)
        if extra:
            self.text(extra, 22, color=GRAY, gap=4)
        self.y += 18

    def jpeg(self) -> bytes:
        self.y += 40
        out = io.BytesIO()
        self.img.crop((0, 0, W, self.y)).save(out, "JPEG", quality=90)
        return out.getvalue()


def pix(valor: float, mensagem: str, when: datetime, para: str = "Marina Salles") -> bytes:
    c = _Canvas(NU_PURPLE)
    c.paste(_logo("nubank", 44))
    c.y += 30
    c.text("Comprovante de transferência", 34, bold=True, gap=8)
    c.text(_data(when), 22, color=GRAY)
    c.rule(20)
    c.text("Valor", 22, color=GRAY, gap=6)
    c.text(_brl(valor), 60, bold=True, color=NU_PURPLE, gap=4)
    c.rule()
    c.field("Tipo de transferência", "Pix", icon=_logo("pix", 30, crop_symbol=True))
    c.field("Destino", para, extra=" · ".join(BANCO_DELA))
    c.field("Origem", "Patrick Ramos", extra="Nu Pagamentos S.A. – Instituição de Pagamento")
    if mensagem:
        c.field("Mensagem", mensagem)
    return c.jpeg()


def pedido(item: str, restaurante: str, total: float, previsao: datetime, observacao: str, when: datetime,
           endereco: str = "Casa da Ma") -> bytes:
    c = _Canvas(IFOOD_RED)
    c.paste(_logo("ifood", 56))
    c.y += 30
    c.text("Pedido confirmado", 34, bold=True, gap=8)
    c.text(f"{restaurante} · {_data(when)}", 22, color=GRAY)
    c.rule(20)
    c.text(f"1x {item}", 28, bold=True, gap=4)
    c.rule()
    c.field("Entrega em", endereco)
    c.field("Previsão de entrega", f"{previsao:%H:%M}")
    if observacao:
        c.field("Observações do pedido", observacao)
    c.rule(8)
    f = _font(30, True)
    c.d.text((PAD, c.y), "Total", font=f, fill=INK)
    total_s = _brl(total)
    c.d.text((W - PAD - c.d.textlength(total_s, font=f), c.y), total_s, font=f, fill=INK)
    c.y += 40
    return c.jpeg()
