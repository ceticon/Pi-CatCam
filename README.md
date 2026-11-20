🐈 Pi-CatCam
A lightweight, motion-activated surveillance camera built with a Raspberry Pi Zero 2 W.

Version 1.8

Pi-CatCam uses a PIR motion sensor to automatically record Full HD video when movement is detected. A Flask web interface provides live video, camera status, infrared illumination controls and a gallery of recorded videos.

The camera supports automatic and manual infrared illumination, digital PIR signal filtering, background MP4 conversion and automatic recovery from camera freezes.
Features
- Full HD recording (1920 × 1080, 25 FPS)
- Motion detection using HC-SR501 PIR sensor
- Configurable digital PIR filter (default: 500 ms)
- PIR diagnostic logging for motion start and end events
- Automatic recording when filtered motion is detected
- Configurable recording delay (default: 10 seconds)
- Automatic H.264 to MP4 conversion using FFmpeg
- Background MP4 conversion without blocking motion detection
- Live MJPEG video streaming (640 × 360)
- Web interface with camera and recording status
- Video gallery with playback directly in the browser
- Delete individual recordings from the video gallery
- Confirmation before permanently deleting recordings
- Infrared night illumination controlled via GPIO18
- Three IR operating modes: OFF / AUTO / ON
- Manual IR mode selection from the web interface
- Automatic IR activation when filtered motion is detected
- IR status indicator in the web interface
- Configurable PIR ignore period after IR activation
- Camera watchdog with automatic restart on stalled video capture
- Automatic startup and restart using systemd
- Optimized for Raspberry Pi Zero 2 W
Hardware
Component	Description
Raspberry Pi	Raspberry Pi Zero 2 W
Camera	Raspberry Pi Camera Module 3 NoIR Wide
Motion sensor	HC-SR501 PIR
IR illumination	Electrokit IR LED module (41024238)
Storage	microSD card


GPIO connections
Component	Signal	Raspberry Pi GPIO	Physical pin
PIR sensor	VCC	5V	Pin 2
PIR sensor	OUT	GPIO17	Pin 11
PIR sensor	GND	GND	Pin 6
IR illumination	5V	5V	Pin 4
IR illumination	EN	GPIO18	Pin 12
IR illumination	GND	GND	Pin 6


The Raspberry Pi uses 3.3V GPIO logic. Ensure that connected devices use compatible signal levels.

The IR illumination is powered from 5V and controlled by GPIO18.
PIR motion detection and filtering
Pi-CatCam v1.8 includes a configurable digital filter for the PIR input on GPIO17.

The PIR signal must remain active continuously for the configured filter time before Pi-CatCam accepts it as valid motion. This helps reject brief pulses that could otherwise start an unwanted recording.

Default settings in catcam.py:
PIR_PIN = 17
PIR_FILTER_TIME = 0.5  # seconds
PIR_DEBUG = True
RECORD_DELAY = 10.0    # seconds
With the default 500 ms filter:
1. A PIR pulse shorter than 500 ms is ignored by the recording logic.
2. A continuously active PIR signal is accepted after approximately 500 ms.
3. Recording starts after accepted motion.
4. Further accepted motion extends the recording.
5. Recording stops after the configured delay without accepted motion.
The main loop checks the PIR signal approximately every 100 ms, so actual detection latency may be slightly longer than the configured filter time.

The filter applies to the recording logic. The web interface's PIR status indicator still shows the raw pir.motion_detected state and may therefore show brief activity that does not trigger recording.
PIR diagnostic logging
When PIR_DEBUG = True, Pi-CatCam logs raw PIR motion transitions:
PIR GPIO17: Rörelse upptäckt
PIR GPIO17: Ingen rörelse
These messages indicate raw sensor activity, not necessarily a recording trigger. Recording starts only after the signal passes the digital filter.

Follow the service log with:
sudo journalctl -u picatcam.service -f
To disable diagnostic messages, set PIR_DEBUG = False in catcam.py and restart the service.

Note: The digital filter reduces short false pulses but cannot distinguish real movement from a sustained electrical or thermal disturbance. If the PIR output remains active longer than the filter time, it can still trigger a recording. Sensor sensitivity, placement, wiring and power supply may also affect reliability.
Infrared illumination
Pi-CatCam supports three IR operating modes.
Mode	Description
OFF	IR illumination is always disabled
AUTO	IR illumination turns on when filtered motion triggers recording and turns off when recording ends
ON	IR illumination remains continuously enabled


Automatic mode
AUTO is the default operating mode.

When the PIR sensor reports motion that passes the digital filter:
1. IR illumination is enabled.
2. Full HD recording starts.
3. Recording continues while accepted motion is detected.
4. When motion stops, recording continues for the configured delay.
5. IR illumination is disabled when recording ends.
The default recording delay is 10 seconds.
Manual IR control
The web interface provides three buttons:

OFF / AUTO / ON

The selected operating mode and current IR output status are displayed on the main page.

Changes take effect immediately without restarting Pi-CatCam.

The IR operating mode is not currently stored permanently. After a restart, Pi-CatCam returns to AUTO mode.
IR configuration
The default configuration is defined in catcam.py:
IR_PIN = 18
IR_DEFAULT_MODE = "AUTO"
IR_MOTION_IGNORE_TIME = 2.0
IR_DEFAULT_MODE determines the operating mode at startup. Available values are "OFF", "AUTO" and "ON".

IR_MOTION_IGNORE_TIME defines a short period after IR activation during which PIR signals do not extend an active recording. This helps reduce the effect of brief disturbances when the IR illumination switches on. It does not eliminate continuous interference from the illumination.

Physical separation or shielding between the IR illumination and PIR sensor may improve reliability.

The IR illumination is switched off during normal program shutdown.

The Camera Module 3 NoIR Wide is sensitive to infrared light, allowing video recording in dark environments.
Software
- Raspberry Pi OS
- Python 3
- Picamera2
- gpiozero
- Flask
- OpenCV
- FFmpeg
Installation
Install system dependencies:
sudo apt update
sudo apt install -y \
    python3-picamera2 \
    python3-gpiozero \
    python3-opencv \
    python3-venv \
    ffmpeg
Clone the repository:
git clone git@github.com:ceticon/Pi-CatCam.git
cd Pi-CatCam
Create a Python virtual environment:
/usr/bin/python3 -m venv --system-site-packages myenv
source myenv/bin/activate
Install Flask:
pip install Flask
Usage
Start Pi-CatCam:
python catcam.py
Open the web interface:
http://<raspberry-pi-ip>:5000
The interface provides:
- Live camera video
- Camera status
- PIR motion detection status (raw signal)
- Recording status (filtered motion)
- IR operating mode selection
- IR output status
- Video gallery
IR control API
The IR operating mode can also be controlled through the Flask API.

Read the current IR status:
GET /api/ir
Example response:
{
    "success": true,
    "mode": "AUTO",
    "enabled": false
}
Change the operating mode:
POST /api/ir
Content-Type: application/json

{
    "mode": "ON"
}
Supported values are OFF, AUTO and ON.

The existing /api/status endpoint also includes IR information.
Video gallery
Open:
http://<raspberry-pi-ip>:5000/gallery
Recorded videos are stored in the videos/ directory.

Videos are initially recorded in H.264 format and automatically converted to MP4 without re-encoding.

MP4 conversion runs in a separate thread, allowing motion detection and new recordings to continue during conversion.
Delete recordings
Each video in the gallery has a Delete button.

When selected:
1. A confirmation dialog is displayed.
2. The selected MP4 file is permanently deleted after confirmation.
3. The video is removed from the gallery.
4. The recording counter is updated automatically.
Deleted recordings cannot be recovered through Pi-CatCam.
Camera Watchdog
Pi-CatCam includes a watchdog that monitors incoming camera frames.

If the camera stops delivering frames for more than 20 seconds, the watchdog terminates the application with an error status.

When Pi-CatCam runs as a systemd service with Restart=on-failure, systemd automatically restarts the application.

Default watchdog settings:
WATCHDOG_TIMEOUT = 20.0
WATCHDOG_STARTUP_DELAY = 30.0
WATCHDOG_INTERVAL = 2.0
The watchdog improves reliability but does not prevent all hardware or camera driver failures.

A forced restart may interrupt an active recording.
Automatic startup with systemd
Create a service file:
sudo nano /etc/systemd/system/picatcam.service
Add:
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
Adjust User, WorkingDirectory and ExecStart to match your installation.

Enable and start the service:
sudo systemctl daemon-reload
sudo systemctl enable picatcam.service
sudo systemctl start picatcam.service
Check service status:
sudo systemctl status picatcam.service
View logs:
journalctl -u picatcam.service -f
Restart the camera:
sudo systemctl restart picatcam.service
Stop the camera:
sudo systemctl stop picatcam.service
Configuration
The main configuration parameters are defined in catcam.py.
Parameter	Default
PIR_PIN	17
PIR_FILTER_TIME	0.5 seconds
PIR_DEBUG	True
IR_PIN	18
IR_DEFAULT_MODE	AUTO
IR_MOTION_IGNORE_TIME	2 seconds
RECORD_DELAY	10 seconds
VIDEO_WIDTH	1920
VIDEO_HEIGHT	1080
FRAMERATE	25
BITRATE	8 Mbps
LIVE_WIDTH	640
LIVE_HEIGHT	360
LIVE_FPS	5
JPEG_QUALITY	70
WATCHDOG_TIMEOUT	20 seconds
WATCHDOG_STARTUP_DELAY	30 seconds
WATCHDOG_INTERVAL	2 seconds


Project structure
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
Security
The Flask web interface is intended for use on a trusted local network.

It does not currently provide authentication and should not be exposed directly to the internet.

Anyone with access to the web interface can change the IR operating mode and potentially delete recordings through the gallery.
Future improvements
- Automatic cleanup of old recordings
- Web-based configuration, including PIR filter time
- Video thumbnails
- Persistent IR mode configuration
- Automatic IR control using ambient light detection
- Improved camera diagnostics
- Optional authentication for the web interface
Version history
v1.8
- Added configurable digital PIR filter (PIR_FILTER_TIME, default 500 ms)
- Require sustained PIR activity before starting or extending a recording
- Added PIR diagnostic logging (PIR_DEBUG) for raw motion transitions
- Improved resistance to brief PIR disturbance pulses
- Updated configuration reference and troubleshooting documentation
v1.7
- Added three IR operating modes: OFF / AUTO / ON
- Added automatic IR activation on PIR motion detection
- Added automatic IR shutdown after recording
- Added manual IR mode selection from the web interface
- Added IR operating mode and output status indicators
- Added /api/ir GET and POST endpoints
- Extended /api/status with IR information
- Added configurable PIR ignore period after IR activation
- Updated documentation
v1.6
- Added infrared illumination control via GPIO18
- Added individual video deletion from the gallery
- Added confirmation before deleting recordings
- Updated documentation and GPIO connections
v1.5
- Added camera watchdog
- Added automatic recovery through systemd
- Added background MP4 conversion
- Improved logging
v1.4
- Full HD motion-activated recording
- Live MJPEG video streaming
- Flask web interface
- Video gallery with MP4 playback
Author
Created by ceticon.
Status
Pi-CatCam v1.8 — Working prototype.

Live video, motion detection, MP4 recording, infrared operating modes and video deletion have been tested successfully.

Initial testing indicates improved PIR stability with the 500 ms digital filter. Long-term watchdog recovery and PIR reliability with infrared illumination remain to be fully v
