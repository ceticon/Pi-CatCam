
#!/usr/bin/env python3

import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from gpiozero import MotionSensor
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

from web.app import (
    init_app,
    update_frame,
    start_webserver
)


# ==========================================
# Pi-CatCam v1.3 - Inställningar
# ==========================================

# PIR-sensor
PIR_PIN = 17

# Eftergångstid i sekunder
RECORD_DELAY = 10.0

# Videoinspelning - Full HD
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FRAMERATE = 25
BITRATE = 8_000_000

# Livevideo - Flask
LIVE_WIDTH = 640
LIVE_HEIGHT = 360
LIVE_FPS = 5
JPEG_QUALITY = 70

# Kataloger
BASE_DIR = Path(__file__).resolve().parent
VIDEO_DIR = BASE_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# Status
# ==========================================

recording = False
last_motion_time = 0.0
current_file = None

stop_event = threading.Event()


def is_recording():
    return recording


# ==========================================
# PIR-sensor
# ==========================================

pir = MotionSensor(PIR_PIN)


# ==========================================
# Kamera
# ==========================================

camera = Picamera2()

config = camera.create_video_configuration(
    main={
        "size": (VIDEO_WIDTH, VIDEO_HEIGHT),
        "format": "YUV420"
    },
    lores={
        "size": (LIVE_WIDTH, LIVE_HEIGHT),
        "format": "YUV420"
    },
    controls={
        "FrameRate": FRAMERATE
    },
    buffer_count=4
)

camera.configure(config)
camera.start()


# ==========================================
# MP4-konvertering
# ==========================================

def convert_to_mp4(h264_file):

    mp4_file = h264_file.with_suffix(".mp4")

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-fflags", "+genpts",
        "-r", str(FRAMERATE),
        "-i", str(h264_file),
        "-c:v", "copy",
        "-movflags", "+faststart",
        str(mp4_file)
    ]

    print("Konverterar till MP4...", flush=True)

    try:
        subprocess.run(command, check=True)

        if not mp4_file.is_file() or mp4_file.stat().st_size == 0:
            raise RuntimeError("MP4-filen saknas eller är tom")

        h264_file.unlink()

        print(
            f"MP4 sparad: {mp4_file.name}",
            flush=True
        )

    except (
        subprocess.CalledProcessError,
        OSError,
        RuntimeError
    ) as error:

        print(
            f"MP4-konvertering misslyckades: {error}",
            flush=True
        )

        print(
            f"Originalfilen behålls: {h264_file.name}",
            flush=True
        )


# ==========================================
# Starta inspelning
# ==========================================

def start_recording():
    global recording, current_file

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S_%f"
    )

    current_file = (
        VIDEO_DIR / f"catcam_{timestamp}.h264"
    )

    encoder = H264Encoder(bitrate=BITRATE)

    camera.start_encoder(
        encoder,
        FileOutput(str(current_file))
    )

    recording = True

    print(
        f"Rörelse! Inspelning startad: "
        f"{current_file.name}",
        flush=True
    )


# ==========================================
# Stoppa inspelning
# ==========================================

def stop_recording():
    global recording

    camera.stop_encoder()
    recording = False

    print(
        "Inspelning avslutad",
        flush=True
    )

    convert_to_mp4(current_file)

    print(
        "Väntar på rörelse...",
        flush=True
    )


# ==========================================
# Livevideo
# ==========================================

def live_video_worker():

    print(
        "Livevideo startad",
        flush=True
    )

    interval = 1.0 / LIVE_FPS

    while not stop_event.is_set():

        start_time = time.monotonic()

        try:

            # Hämta bild från lores-strömmen
            yuv = camera.capture_array("lores")

            # Konvertera YUV420 till BGR
            bgr = cv2.cvtColor(
                yuv,
                cv2.COLOR_YUV2BGR_I420
            )

            # Koda bilden som JPEG
            success, jpeg = cv2.imencode(
                ".jpg",
                bgr,
                [
                    cv2.IMWRITE_JPEG_QUALITY,
                    JPEG_QUALITY
                ]
            )

            if success:
                update_frame(
                    jpeg.tobytes()
                )

        except Exception as error:

            if not stop_event.is_set():
                print(
                    f"Livevideo-fel: {error}",
                    flush=True
                )

                time.sleep(0.5)

        elapsed = (
            time.monotonic() - start_time
        )

        stop_event.wait(
            max(0, interval - elapsed)
        )

    print(
        "Livevideo stoppad",
        flush=True
    )


# ==========================================
# Flask
# ==========================================

init_app(
    camera,
    pir,
    is_recording
)

web_thread = threading.Thread(
    target=start_webserver,
    daemon=True
)

live_thread = threading.Thread(
    target=live_video_worker,
    daemon=True
)


# ==========================================
# Startinformation
# ==========================================

print("================================")
print("        Pi-CatCam v1.3")
print("================================")
print(
    f"Inspelning: {VIDEO_WIDTH}x{VIDEO_HEIGHT}"
)
print(
    f"Livevideo: {LIVE_WIDTH}x{LIVE_HEIGHT}"
)
print(
    f"Live FPS: {LIVE_FPS}"
)
print(
    f"Eftergångstid: {RECORD_DELAY} sek"
)

web_thread.start()
live_thread.start()

print(
    "Webbserver: http://0.0.0.0:5000"
)

print(
    "Väntar på rörelse...",
    flush=True
)


# ==========================================
# Huvudprogram
# ==========================================

try:

    while True:

        now = time.monotonic()

        # Rörelse upptäckt
        if pir.motion_detected:

            last_motion_time = now

            if not recording:
                start_recording()

        # Ingen rörelse
        elif recording:

            elapsed = (
                now - last_motion_time
            )

            if elapsed >= RECORD_DELAY:
                stop_recording()

        time.sleep(0.1)

except KeyboardInterrupt:

    print(
        "\nAvslutar Pi-CatCam...",
        flush=True
    )

finally:

    stop_event.set()

    live_thread.join(timeout=3.0)

    if recording:
        stop_recording()

    camera.stop()
    camera.close()
    pir.close()

    print(
        "Pi-CatCam stoppad",
        flush=True
    )
