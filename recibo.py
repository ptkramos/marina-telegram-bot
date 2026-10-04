"""Comprovantes do Mini App (opção B, Patrick 25/09): imagem com cara de comprovante do
Nubank (pix) ou de pedido do iFood, postada no chat como mensagem DELE (answerWebAppQuery).
Uso pessoal: marcas reais, logos do Wikimedia Commons (domínio público) em webapp/marcas/.
"""
from __future__ import annotations

import io
import re
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


def _wrap(text: str, font, width: int) -> list[str]:
    """Quebra por largura real em pixels (não por nº de letras), pra nada passar da margem."""
    lines, cur = [], ""
    for word in (text or "").split():
        test = f"{cur} {word}".strip()
        if cur and font.getlength(test) > width:
            lines.append(cur)
            cur = word
        else:
            cur = test
    return lines + [cur] if cur else lines or [""]


def _data(when: datetime) -> str:
    return f"{when.day:02d} {MESES[when.month - 1]} {when.year}, {when:%H:%M}"


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
        """Rótulo cinza, valor em negrito (sempre: 26/09 o Patrick pediu alinhamento e padrão iguais em tudo)."""
        self.text(label, 22, color=GRAY, gap=6)
        x = PAD
        f = _font(28, True)
        if icon is not None:            # ícone centrado na altura da 1ª linha do valor
            top, bottom = f.getbbox("Ág")[1], f.getbbox("Ág")[3]
            self.img.paste(icon, (PAD, self.y + (top + bottom - icon.height) // 2), icon)
            x = PAD + icon.width + 12
        for line in _wrap(value, f, W - PAD - x):
            self.text(line, 28, bold=True, gap=4, x=x)
        if extra:
            self.text(extra, 22, color=GRAY, gap=4, x=x)
        self.y += 18

    def row(self, left: str, right: str, size: int = 24, *, bold=False, color=GRAY):
        """Linha de valores: rótulo à esquerda, valor colado na margem direita, mesma linha de base."""
        f = _font(size, bold)
        self.d.text((PAD, self.y), left, font=f, fill=color)
        self.d.text((W - PAD - self.d.textlength(right, font=f), self.y), right, font=f, fill=color)
        self.y += f.getbbox("Ág")[3] + 12

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
    c.field("Destino", para, extra=f"{BANCO_DELA[0]} ({BANCO_DELA[1]})")
    c.field("Origem", "Patrick Ramos", extra="Nu Pagamentos S.A. – Instituição de Pagamento")
    if mensagem:
        c.field("Mensagem", mensagem)
    return c.jpeg()


def pedido(itens, restaurante: str, total: float, previsao: datetime, observacao: str, when: datetime,
           endereco: str = "Casa da Ma", *, taxa: Optional[float] = None, servico: Optional[float] = None,
           logo_loja: Optional[Path] = None) -> bytes:
    """itens: lista de {"qtd", "nome", "preco"} (preço da linha) ou, no formato antigo, texto."""
    c = _Canvas(IFOOD_RED)
    c.paste(_logo("ifood", 56))
    c.y += 30
    c.text("Pedido confirmado", 34, bold=True, gap=8)
    c.text(_data(when), 22, color=GRAY, gap=0)
    c.rule(20)
    # loja: logo redondo + nome, centrados na mesma linha
    x = PAD
    if logo_loja and Path(logo_loja).exists():
        lg = Image.open(logo_loja).convert("RGBA").resize((64, 64), Image.LANCZOS)
        mask = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 63, 63), fill=255)
        c.img.paste(lg, (PAD, c.y), mask)
        c.d.ellipse((PAD, c.y, PAD + 63, c.y + 63), outline=LINE, width=2)
        x = PAD + 64 + 18
    f = _font(28, True)
    c.d.text((x, c.y + 32), restaurante, font=f, fill=INK, anchor="lm")
    c.y += 64 + 26
    # itens em colunas: quantidade numa caixinha | nome (2ª linha recuada sob o nome) | preço à direita
    if isinstance(itens, str):
        itens = [itens]
    f, fq = _font(26), _font(22, True)
    box, gap = 38, 16
    col_nome = PAD + box + gap
    for it in itens:
        if isinstance(it, str):
            m = re.match(r"(\d+)x (.+)", it)
            qtd, nome, preco = (int(m.group(1)), m.group(2), None) if m else (1, it, None)
        else:
            qtd, nome, preco = it["qtd"], it["nome"], it.get("preco")
        preco_s = _brl(preco) if preco is not None else ""
        largura = W - PAD - col_nome - (int(c.d.textlength(preco_s, font=f)) + 24 if preco_s else 0)
        linhas = _wrap(nome, f, largura)
        h = f.getbbox("Ág")[3]
        c.d.rounded_rectangle((PAD, c.y, PAD + box - 1, c.y + box - 1), radius=6, outline=LINE, width=2)
        c.d.text((PAD + box // 2, c.y + box // 2), str(qtd), font=fq, fill=INK, anchor="mm")
        base = c.y + box // 2
        for n, line in enumerate(linhas):
            c.d.text((col_nome, base + n * (h + 6)), line, font=f, fill=INK, anchor="lm")
        if preco_s:
            c.d.text((W - PAD, base), preco_s, font=f, fill=INK, anchor="rm")
        c.y += max(box, box // 2 + (len(linhas) - 1) * (h + 6) + h // 2 + 4) + 16
    c.rule(14)
    c.field("Entrega em", endereco)
    c.field("Previsão de entrega", f"{previsao:%H:%M}")
    if observacao:
        c.field("Observações do pedido", observacao)
    c.rule(8)
    if taxa is not None and servico is not None:
        c.row("Subtotal", _brl(total - taxa - servico))
        c.row("Taxa de entrega", _brl(taxa) if taxa else "Grátis")
        c.row("Taxa de serviço", _brl(servico))
        c.y += 6
    c.row("Total", _brl(total), 30, bold=True, color=INK)
    return c.jpeg()
