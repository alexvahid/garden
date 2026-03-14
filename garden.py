import time
import sys
import board
import busio
from adafruit_ads1x15 import ADS1015, AnalogIn, ads1x15
import RPi.GPIO as GPIO
import boto3
from datetime import datetime, timedelta

DEBUG = '--debug' in sys.argv

# GPIO Setup
RELAY1_PIN = 26  # Low water section
RELAY2_PIN = 20  # Medium water section
RELAY3_PIN = 21  # High water section
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY1_PIN, GPIO.OUT)
GPIO.setup(RELAY2_PIN, GPIO.OUT)
GPIO.setup(RELAY3_PIN, GPIO.OUT)
GPIO.output(RELAY1_PIN, GPIO.LOW)
GPIO.output(RELAY2_PIN, GPIO.LOW)
GPIO.output(RELAY3_PIN, GPIO.LOW)

# Watering durations - based on 12 GPM flow rate
# In DEBUG mode, values are seconds; otherwise minutes (converted to seconds)
DURATIONS = {
    RELAY1_PIN: 2   if DEBUG else 2   * 60,   # low water
    RELAY2_PIN: 4   if DEBUG else 4   * 60,   # medium water
    RELAY3_PIN: 6   if DEBUG else 6   * 60    # high water
}

# Moisture threshold (adjust based on your sensor calibration)
WET_THRESHOLD = 9000

# AWS Setup
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

# Sensor Setup
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS1015(i2c)
chan = AnalogIn(ads, ads1x15.Pin.A0)

last_metric_time = datetime.now()
last_watering = datetime.now() - timedelta(hours=24)
relay_start_times = {}

def get_cpu_temp():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            return float(f.read()) / 1000.0 * 9/5 + 32
    except:
        return None

def send_metrics():
    try:
        moisture = chan.value
        cpu_temp = get_cpu_temp()
        metrics = []
        if moisture is not None:
            metrics.append({'MetricName': 'SoilMoisture', 'Value': moisture, 'Unit': 'None'})
        if cpu_temp is not None:
            metrics.append({'MetricName': 'CPUTemperature', 'Value': cpu_temp, 'Unit': 'None'})
        if metrics:
            cloudwatch.put_metric_data(Namespace='RaspberryPiGarden', MetricData=metrics)
            if DEBUG:
                print(f"[{datetime.now():%H:%M:%S}] Metrics sent — moisture={moisture}, cpu_temp={cpu_temp}°F")
    except Exception as e:
        print(f"Metric error: {e}")

def water_section(pin, duration):
    try:
        relay_num = {RELAY1_PIN: 1, RELAY2_PIN: 2, RELAY3_PIN: 3}[pin]
        print(f"[{datetime.now():%H:%M:%S}] Relay {relay_num} ON (pin {pin}) for {duration}s")
        relay_start_times[pin] = time.time()
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(pin, GPIO.LOW)
        elapsed = time.time() - relay_start_times[pin]
        print(f"[{datetime.now():%H:%M:%S}] Relay {relay_num} OFF — ran {elapsed:.1f}s")
        cloudwatch.put_metric_data(
            Namespace='RaspberryPiGarden',
            MetricData=[{'MetricName': f'Relay{relay_num}Duration', 'Value': elapsed, 'Unit': 'Seconds'}]
        )
    except Exception as e:
        print(f"Watering error on pin {pin}: {e}")
        try:
            GPIO.output(pin, GPIO.LOW)
        except:
            pass

try:
    while True:
        try:
            now = datetime.now()
            
            # Hourly metrics (every minute in DEBUG)
            if (now - last_metric_time).total_seconds() >= (10 if DEBUG else 3600):
                send_metrics()
                last_metric_time = now
            
            # Daily watering at 6 AM (any hour in DEBUG, no cooldown in DEBUG)
            if (DEBUG or now.hour == 6) and (DEBUG or (now - last_watering).total_seconds() >= 21600):
                try:
                    moisture = chan.value
                    if DEBUG:
                        print(f"[{now:%H:%M:%S}] Checking moisture: {moisture} (threshold={WET_THRESHOLD})")
                    if moisture > WET_THRESHOLD:
                        print(f"[{now:%H:%M:%S}] Starting watering cycle")
                        for pin in [RELAY1_PIN, RELAY2_PIN, RELAY3_PIN]:
                            water_section(pin, DURATIONS[pin])
                        last_watering = now
                        print(f"[{now:%H:%M:%S}] Watering cycle complete")
                    else:
                        print("Skipping watering - soil is wet")
                except Exception as e:
                    print(f"Watering cycle error: {e}")
            
            time.sleep(1 if DEBUG else 60)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(1 if DEBUG else 60)
        
except KeyboardInterrupt:
    GPIO.cleanup()