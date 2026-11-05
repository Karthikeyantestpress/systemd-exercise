import os
import time
import signal
import sys
import logging


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "5"))
CRASH_AFTER = int(os.environ.get("CRASH_AFTER", "0"))
LEAK_MB_PER_BEAT = int(os.environ.get("LEAK_MB_PER_BEAT", "0"))

running = True

def handle_stop(signum, frame):
    global running
    logging.info("Received %s. Finishing current work...", signal.Signals(signum).name)
    running = False

signal.signal(signal.SIGTERM, handle_stop)
signal.signal(signal.SIGINT, handle_stop)

logging.info("Started with PID %s", os.getpid())
beats = 0
leak = []

while running:
    beats += 1
    logging.info("Heartbeat %s from PID %s", beats, os.getpid())

    if LEAK_MB_PER_BEAT:
        leak.append(b"x" * (LEAK_MB_PER_BEAT * 1024 * 1024))
        logging.info("Holding %s MB of extra memory", beats * LEAK_MB_PER_BEAT)

    if CRASH_AFTER and beats >= CRASH_AFTER:
        raise RuntimeError("Simulated crash")

    time.sleep(HEARTBEAT_INTERVAL)

logging.info("Shutdown complete. Exiting cleanly.")