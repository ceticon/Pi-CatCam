
# 🐈 Pi-CatCam

A lightweight, motion-activated surveillance camera built with a Raspberry Pi Zero 2 W.

Pi-CatCam uses a PIR motion sensor to automatically record Full HD video when movement is detected. A Flask web interface provides live video, camera status and a gallery of recorded videos.

## Features

- Full HD recording (1920 × 1080, 25 FPS)
- Motion detection using HC-SR501 PIR sensor
- Automatic recording when motion is detected
- Configurable recording delay (default: 10 seconds)
- Automatic H.264 to MP4 conversion using FFmpeg
- Live MJPEG video streaming (640 × 360)
- Web interface with camera and recording status
- Video gallery with playback directly in the browser
- Optimized for Raspberry Pi Zero 2 W

## Hardware

| Component | Description |
|-----------|-------------|
| Raspberry Pi | Raspberry Pi Zero 2 W |
| Camera | Raspberry Pi Camera Module 3 NoIR Wide |
| Motion sensor | HC-SR501 PIR |
| IR illumination | External infrared LED spotlight |
| Storage | microSD card |

### PIR sensor wiring

| HC-SR501 | Raspberry Pi |
|----------|--------------|
| VCC | 5V (Pin 2 or 4) |
| OUT | GPIO17 (Pin 11) |
| GND | GND (Pin 6) |

Make sure the PIR output is compatible with the Raspberry Pi's 3.3V GPIO inputs.

## Software

- Raspberry Pi OS
- Python 3
- Picamera2
- gpiozero
- Flask
- OpenCV
- FFmpeg

## Installation

Install system dependencies:

```bash
sudo apt update
sudo apt install -y \
    python3-picamera2 \
    python3-gpiozero \
    python3-opencv \
    python3-venv \
    ffmpeg
```

Clone the repository:

```bash
git clone git@github.com:ceticon/Pi-CatCam.git
cd Pi-CatCam
```

Create a Python virtual environment:

```bash
/usr/bin/python3 -m venv --system-site-packages myenv
source myenv/bin/activate
```

Install Flask:

```bash
pip install Flask
```

## Usage

Start Pi-CatCam:

```bash
python catcam.py
```

Open the web interface:

```text
http://<raspberry-pi-ip>:5000
```

The interface provides:

- Live camera video
- Camera status
- PIR motion detection status
- Recording status
- Video gallery

### Video gallery

Open:

```text
http://<raspberry-pi-ip>:5000/gallery
```

Recorded videos are stored in the `videos/` directory.

Videos are recorded in H.264 format and automatically converted to MP4 without re-encoding.

## Configuration

The main configuration parameters are defined in `catcam.py`.

| Parameter | Default |
|-----------|---------|
| PIR_PIN | 17 |
| RECORD_DELAY | 10 seconds |
| VIDEO_WIDTH | 1920 |
| VIDEO_HEIGHT | 1080 |
| FRAMERATE | 25 |
| BITRATE | 8 Mbps |
| LIVE_WIDTH | 640 |
| LIVE_HEIGHT | 360 |
| LIVE_FPS | 5 |
| JPEG_QUALITY | 70 |

## Project structure

```text
Pi-CatCam/
├── catcam.py
├── pir_test.py
├── web/
│   ├── app.py
│   ├── static/
│   │   └── style.css
│   └── templates/
│       ├── index.html
│       └── gallery.html
└── videos/          # Created automatically
```

## Security

The Flask web interface is intended for use on a trusted local network.

It does not currently provide authentication and should not be exposed directly to the internet.

## Future improvements

- Automatic cleanup of old recordings
- Web-based configuration
- Video thumbnails
- Automatic startup using systemd
- Improved infrared night recording

## Author

Created by [ceticon](https://github.com/ceticon).

## Status

Pi-CatCam v1.4 — Working prototype.
