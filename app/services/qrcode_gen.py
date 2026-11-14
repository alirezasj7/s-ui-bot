from __future__ import annotations

"""Generate subscription QR codes (optional branded background)."""

from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

from app.config import DATA_DIR


UPLOADS_DIR = DATA_DIR / "uploads"


def uploads_dir() -> Path:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOADS_DIR


def resolve_media_path(relative: str | None) -> Path | None:
    if not relative:
        return None
    rel = str(relative).strip().lstrip("/").replace("\\", "/")
    if not rel or ".." in rel:
        return None
    path = DATA_DIR / rel
    if path.is_file():
        return path
    # also allow uploads/foo stored as bare filename
    alt = uploads_dir() / Path(rel).name
    return alt if alt.is_file() else None


def make_subscription_qr(
    url: str,
    *,
    background: str | None = None,
    box_size: int = 10,
    border: int = 2,
) -> BytesIO:
    """Return PNG bytes of a QR for the subscription URL."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

    bg_path = resolve_media_path(background)
    if bg_path:
        try:
            bg = Image.open(bg_path).convert("RGBA")
            # Shrink QR a bit so more of the branded background stays visible
            shrink = 0.82
            qw = max(1, int(qr_img.size[0] * shrink))
            qh = max(1, int(qr_img.size[1] * shrink))
            qr_img = qr_img.resize((qw, qh), Image.Resampling.LANCZOS)
            # Larger canvas margin around the QR plate
            side = max(qr_img.size) + 140
            canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
            # cover-fit background
            bw, bh = bg.size
            scale = max(side / bw, side / bh)
            nw, nh = int(bw * scale), int(bh * scale)
            bg = bg.resize((nw, nh), Image.Resampling.LANCZOS)
            canvas.paste(bg, ((side - nw) // 2, (side - nh) // 2))
            # Rounded white plate behind QR for readability
            pad = 20
            radius = 18
            pw, ph = qr_img.size[0] + pad * 2, qr_img.size[1] + pad * 2
            plate = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(plate).rounded_rectangle(
                (0, 0, pw - 1, ph - 1),
                radius=radius,
                fill=(255, 255, 255, 230),
            )
            px = (side - pw) // 2
            py = (side - ph) // 2
            canvas.paste(plate, (px, py), plate)
            canvas.paste(qr_img, (px + pad, py + pad), qr_img)
            out_img = canvas.convert("RGB")
        except Exception:
            out_img = qr_img.convert("RGB")
    else:
        out_img = qr_img.convert("RGB")

    buf = BytesIO()
    out_img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    buf.name = "subscription_qr.png"
    return buf
