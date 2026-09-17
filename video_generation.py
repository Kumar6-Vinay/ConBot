"""
video_generation.py - 20-Second Video Engine for ConBot
Generates a 20-second vertical video (9:16) with Ken Burns pan/zoom,
crossfade transitions, and background ambient audio.
"""
import os
import tempfile
import urllib.request
from typing import List
from PIL import Image
import numpy as np
from moviepy.editor import (
    ImageClip,
    CompositeVideoClip,
    AudioClip
)

TARGET_DURATION = 20.0  # Exactly 20.0 seconds
TARGET_RESOLUTION = (720, 1280)  # 9:16 Vertical format (Reels/Stories/Telegram)


def create_20s_video_from_images(
    image_sources: List[str],  # Can be image URLs or local file paths
    output_path: str,
    fps: int = 24,
    add_audio: bool = True
) -> str:
    """
    Combines an array of images into an exact 20-second cinematic video.
    """
    if not image_sources:
        raise ValueError("At least 1 image is required to generate a video.")

    num_images = len(image_sources)
    overlap = 0.8 if num_images > 1 else 0.0
    slide_duration = (TARGET_DURATION + (num_images - 1) * overlap) / num_images

    clips = []
    temp_files = []

    try:
        start_time = 0.0

        for idx, src in enumerate(image_sources):
            # 1. Download if URL, or use local path
            if src.startswith("http://") or src.startswith("https://"):
                req = urllib.request.Request(
                    src,
                    headers={"User-Agent": "ConBot-Video/1.0"}
                )
                with urllib.request.urlopen(req) as resp:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                    tmp.write(resp.read())
                    tmp.flush()
                    img_path = tmp.name
                    temp_files.append(img_path)
            else:
                img_path = src

            # 2. Crop & fit to 9:16 canvas
            pil_img = Image.open(img_path).convert("RGB")
            tw, th = TARGET_RESOLUTION
            iw, ih = pil_img.size

            scale = max(tw / iw, th / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), Image.Resampling.LANCZOS)

            left = (nw - tw) // 2
            top = (nh - th) // 2
            cropped = pil_img.crop((left, top, left + tw, top + th))

            c_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            cropped.save(c_tmp.name, "JPEG", quality=92)
            temp_files.append(c_tmp.name)

            # 3. Ken Burns subtle zoom
            clip = ImageClip(c_tmp.name).set_duration(slide_duration)
            clip = clip.resize(lambda t: 1.0 + 0.05 * (t / slide_duration))

            if idx > 0:
                clip = clip.crossfadein(overlap)

            clip = clip.set_start(start_time)
            clips.append(clip)

            start_time += (slide_duration - overlap)

        video = CompositeVideoClip(clips, size=TARGET_RESOLUTION).set_duration(TARGET_DURATION)

        # 4. Procedural ambient background chord
        if add_audio:
            def make_frame(t):
                envelope = np.sin(np.pi * t / TARGET_DURATION) * 0.08
                tone = (
                    np.sin(2 * np.pi * 220.0 * t) +
                    np.sin(2 * np.pi * 277.18 * t) * 0.7 +
                    np.sin(2 * np.pi * 329.63 * t) * 0.5
                )
                return envelope * tone

            audio = AudioClip(make_frame, duration=TARGET_DURATION)
            video = video.set_audio(audio)

        # 5. Export MP4
        video.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac" if add_audio else None,
            preset="fast",
            threads=4,
            logger=None
        )

        return output_path

    finally:
        for f in temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass