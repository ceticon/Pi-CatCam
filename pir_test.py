from gpiozero import MotionSensor
from signal import pause

pir = MotionSensor(17)

print("Pi-CatCam PIR-test")
print("Väntar på rörelse...")

def motion_detected():
    print("🐈 Rörelse upptäckt!")

def motion_stopped():
    print("Ingen rörelse längre.")

pir.when_motion = motion_detected
pir.when_no_motion = motion_stopped

pause()
