# 🐈 Pi-CatCam

A lightweight, motion-activated surveillance camera built with a Raspberry Pi Zero 2 W.

**Version 1.6**

Pi-CatCam uses a PIR motion sensor to automatically record Full HD video when movement is detected. A Flask web interface provides live video, camera status and a gallery of recorded videos.

The camera supports infrared night illumination, background MP4 conversion and automatic recovery from camera freezes.

## Features

- Full HD recording (1920 × 1080, 25 FPS)
- Motion detection using HC-SR501 PIR sensor
- Automatic recording when motion is detected
- Configurable recording delay (default: 10 seconds)
- Automatic H.264 to MP4 conversion using FFmpeg
- Background MP4 conversion without blocking motion detection
- Live MJPEG video streaming (640 × 360)
- Web interface with camera and recording status
- Video gallery with playback directly in the browser
- Delete individual recordings from the video gallery
- Confirmation before permanently deleting recordings
- Infrared night illumination controlled via GPIO18
- Camera watchdog with automatic restart on stalled video capture
- Automatic startup and restart using systemd
- Optimized for Raspberry Pi Zero 2 W

## Hardware

| Component | Description |
|---|---|
| Raspberry Pi | Raspberry Pi Zero 2 W |
| Camera | Raspberry Pi Camera Module 3 NoIR Wide |
| Motion sensor | HC-SR501 PIR |
| IR illumination | Electrokit IR LED module (41024238) |
| Storage | microSD card |

### GPIO connections

| Component | Signal | Raspberry Pi GPIO | Physical pin |
|---|---|---|---|
| PIR sensor | VCC | 5V | Pin 2 |
| PIR sensor | OUT | GPIO17 | Pin 11 |
| PIR sensor | GND | GND | Pin 6 |
| IR illumination | 5V | 5V | Pin 4 |
| IR illumination | EN | GPIO18 | Pin 12 |
| IR illumination | GND | GND | Pin 6 |

The Raspberry Pi uses 3.3V GPIO logic. Ensure that connected devices use compatible signal levels.

The IR illumination is powered from 5V and controlled by GPIO18.

### Infrared illumination

The IR illumination is automatically enabled when Pi-CatCam starts.

```python
IR_PIN = 18
IR_ENABLED = True
```

To disable the IR illumination, change:

```python
IR_ENABLED = False
```

The IR illumination is switched off during normal program shutdown.

The Camera Module 3 NoIR Wide is sensitive to infrared light, allowing video recording in dark environments.

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

Videos are initially recorded in H.264 format and automatically converted to MP4 without re-encoding.

MP4 conversion runs in a separate thread, allowing motion detection and new recordings to continue during conversion.

### Delete recordings

Each video in the gallery has a **Delete** button.

When selected:

1. A confirmation dialog is displayed.
2. The selected MP4 file is permanently deleted after confirmation.
3. The video is removed from the gallery.
4. The recording counter is updated automatically.

Deleted recordings cannot be recovered through Pi-CatCam.

## Camera Watchdog

Pi-CatCam includes a watchdog that monitors incoming camera frames.

If the camera stops delivering frames for more than 20 seconds, the watchdog terminates the application with an error status.

When Pi-CatCam runs as a systemd service with `Restart=on-failure`, systemd automatically restarts the application.

Default watchdog settings:

```python
WATCHDOG_TIMEOUT = 20.0
WATCHDOG_STARTUP_DELAY = 30.0
WATCHDOG_INTERVAL = 2.0
```

The watchdog improves reliability but does not prevent all hardware or camera driver failures.

A forced restart may interrupt an active recording.

## Automatic startup with systemd

Create a service file:

```bash
sudo nano /etc/systemd/system/picatcam.service
```

Add:

```ini
[Unit]
Description=Pi-CatCam - Motion Activated Camera
After=multi-user.target

[Service]
Type=simple
User=nic
WorkingDirectory=/home/nic/Projects/Cat-Cam
ExecStart=/home/nic/Projects/Cat-Cam/myenv/bin/python /home/nic/Projects/Cat-Cam/catcam.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Adjust `User`, `WorkingDirectory` and `ExecStart` to match your installation.

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable picatcam.service
sudo systemctl start picatcam.service
```

Check service status:

```bash
sudo systemctl status picatcam.service
```

View logs:

```bash
journalctl -u picatcam.service -f
```

Restart the camera:

```bash
sudo systemctl restart picatcam.service
```

Stop the camera:

```bash
sudo systemctl stop picatcam.service
```

## Configuration

The main configuration parameters are defined in `catcam.py`.

| Parameter | Default |
|---|---|
| PIR_PIN | 17 |
| IR_PIN | 18 |
| IR_ENABLED | True |
| RECORD_DELAY | 10 seconds |
| VIDEO_WIDTH | 1920 |
| VIDEO_HEIGHT | 1080 |
| FRAMERATE | 25 |
| BITRATE | 8 Mbps |
| LIVE_WIDTH | 640 |
| LIVE_HEIGHT | 360 |
| LIVE_FPS | 5 |
| JPEG_QUALITY | 70 |
| WATCHDOG_TIMEOUT | 20 seconds |
| WATCHDOG_STARTUP_DELAY | 30 seconds |
| WATCHDOG_INTERVAL | 2 seconds |

## Project structure

```text
Pi-CatCam/
├── catcam.py
├── pir_test.py
├── README.md
├── requirements.txt
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

Anyone with access to the web interface can potentially delete recordings through the gallery.

## Future improvements

- Automatic cleanup of old recordings
- Web-based configuration
- Video thumbnails
- Manual IR control from the web interface
- Automatic IR control using ambient light detection
- Improved camera diagnostics
- Optional authentication for the web interface

## Version history

### v1.6

- Added infrared illumination control via GPIO18
- Added individual video deletion from the gallery
- Added confirmation before deleting recordings
- Updated documentation and GPIO connections

### v1.5

- Added camera watchdog
- Added automatic recovery through systemd
- Added background MP4 conversion
- Improved logging

### v1.4

- Full HD motion-activated recording
- Live MJPEG video streaming
- Flask web interface
- Video gallery with MP4 playback

## Author

Created by [ceticon](https://github.com/ceticon).

## Status

**Pi-CatCam v1.6 — Working prototype.**

Live video, motion detection, MP4 recording, infrared illumination and video deletion have been tested successfully.

Long-term watchdog recovery remains to be fully verified.
