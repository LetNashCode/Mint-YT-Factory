"""Build an appealing 16:9 YouTube thumbnail from the story's Pexels media.

No new image provider is used: the thumbnail is derived from the same Pexels
asset selected for the current story, with a bold curiosity headline.
"""
from __future__ import annotations
import os, re, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

W, H = 1280, 720


def _font_path():
    candidates = [
        Path("assets/Fonts/Poppins-ExtraBold.ttf"),
        Path("assets/Fonts/Poppins-Bold.ttf"),
        Path("assets/Fonts/Poppins-SemiBold.ttf"),
    ]
    for path in candidates:
        if path.exists(): return str(path)
    return None


def _font(size):
    path = _font_path()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _short_headline(script):
    title = str(script.get("title") or script.get("topic") or "You Won't Believe This").strip()
    title = re.sub(r"[.!?]+$", "", title)
    topic = str(script.get("topic") or "").strip()
    # Prefer a short curiosity hook rather than copying the whole YouTube title.
    patterns = [
        (r"^why (.+)$", lambda m: f"WHY DOES {m.group(1).upper()}?"),
        (r"^how (.+)$", lambda m: f"HOW DOES THIS WORK?"),
        (r"^what (.+)$", lambda m: f"WHAT'S REALLY HAPPENING?"),
    ]
    for pattern, fn in patterns:
        match = re.match(pattern, topic, re.I)
        if match:
            candidate = fn(match)
            if len(candidate) <= 34: return candidate
    # Strip common filler and keep the strongest words.
    cleaned = re.sub(r"\b(the|a|an|your|you|is|are|does|do|why|how)\b", " ", title, flags=re.I)
    cleaned = " ".join(cleaned.split()).upper()
    if len(cleaned) <= 32: return cleaned
    words = cleaned.split(); out=[]
    for word in words:
        if len(" ".join(out+[word])) > 30: break
        out.append(word)
    return " ".join(out) or "YOU NEVER NOTICED THIS"


def _cover_crop(image):
    image = image.convert("RGB")
    ratio = max(W / image.width, H / image.height)
    nw, nh = int(image.width * ratio), int(image.height * ratio)
    image = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left, top = max(0, (nw-W)//2), max(0, (nh-H)//2)
    return image.crop((left, top, left+W, top+H))


def _source_image(media_paths):
    for path in media_paths:
        if not path or not os.path.exists(path): continue
        suffix = Path(path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            try: return Image.open(path)
            except Exception: pass
        if suffix in {".mp4", ".mov", ".webm"}:
            try:
                from moviepy.editor import VideoFileClip
                clip = VideoFileClip(path, audio=False)
                try:
                    frame = clip.get_frame(min(0.7, max(0.1, float(clip.duration)/3)))
                    return Image.fromarray(frame)
                finally: clip.close()
            except Exception as exc:
                print(f"⚠️ Thumbnail video frame extraction failed: {exc}")
    return None


def build_thumbnail(script, media_groups, output_path):
    paths = []
    for group in media_groups or []:
        if isinstance(group, (list, tuple)): paths.extend(group)
    image = _source_image(paths)
    if image is None:
        raise RuntimeError("Cannot build thumbnail: no usable Pexels media asset was produced.")
    image = _cover_crop(image)
    # Slightly punchier, still natural treatment.
    image = ImageEnhance.Contrast(image).enhance(1.10)
    image = ImageEnhance.Color(image).enhance(1.08)
    draw = ImageDraw.Draw(image, "RGBA")
    # Dark left-to-right readability layer, while preserving the subject.
    overlay = Image.new("RGBA", (W,H), (0,0,0,0)); od = ImageDraw.Draw(overlay, "RGBA")
    for x in range(W):
        alpha = int(185 * max(0, 1 - x/(W*0.82)))
        od.line((x,0,x,H), fill=(0,0,0,alpha))
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(image, "RGBA")
    headline = _short_headline(script)
    # Fit the headline to a compact 2-4 line block.
    size = 86
    while size >= 52:
        font = _font(size)
        lines = textwrap.wrap(headline, width=16)
        if max(draw.textbbox((0,0), line, font=font)[2] for line in lines) <= 650: break
        size -= 4
    font = _font(size)
    lines = textwrap.wrap(headline, width=16)[:4]
    line_gap = 8
    heights = [draw.textbbox((0,0), line, font=font, stroke_width=2)[3] for line in lines]
    total = sum(heights) + line_gap*(len(lines)-1)
    y = (H-total)//2
    for line, line_h in zip(lines, heights):
        # Shadow + crisp white text.
        draw.text((64+4,y+5), line, font=font, fill=(0,0,0,180), stroke_width=3, stroke_fill=(0,0,0,180))
        draw.text((64,y), line, font=font, fill=(255,255,255,255), stroke_width=2, stroke_fill=(0,0,0,220))
        y += line_h + line_gap
    # Small curiosity badge.
    badge_font = _font(30)
    badge = "WAIT…"
    bb = draw.textbbox((0,0), badge, font=badge_font)
    pad_x, pad_y = 18, 10
    bx, by = 64, 48
    draw.rounded_rectangle((bx,by,bx+(bb[2]-bb[0])+pad_x*2,by+(bb[3]-bb[1])+pad_y*2), radius=14, fill=(255,255,255,235))
    draw.text((bx+pad_x,by+pad_y-2), badge, font=badge_font, fill=(0,0,0,255))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "JPEG", quality=94, optimize=True, progressive=True)
    print(f"🖼️ Thumbnail created: {output_path} | headline={headline!r}")
    return output_path
