# Testpress Worker: Linux Processes and systemd

A small Python background service managed by systemd, without Docker, Supervisor or PM2. It's used to show how Linux processes behave, how systemd handles failures, and how to diagnose them.

The results and explanations for each experiment are in [experiments.md](experiments.md), and the screenshots are in [evidence/](evidence/).

## Files

| File | Purpose |
|---|---|
| `app.py` | The Python service |
| `testpress-worker.service` | The systemd unit file |
| `testpress-worker.env` | Default settings for the service |
| `experiments.md` | What I ran, expected, observed and why it happened |
| `evidence/` | Screenshots from running the experiments |

## What the service does

- Logs a heartbeat every 5 seconds to standard output, which systemd sends to journald.
- Handles SIGTERM and SIGINT by finishing the current loop, then exiting with code `0`.
- Can crash or leak memory on purpose, controlled by environment variables.
- Runs as a dedicated non-root user, `testpress`.
- Restarts after failures, starts at boot, and has memory and CPU limits.

## Settings

Installed at `/etc/testpress-worker.env`:

| Variable | Default | Meaning |
|---|---|---|
| `HEARTBEAT_INTERVAL` | `5` | Seconds between heartbeats |
| `CRASH_AFTER` | `0` | Crash after this many heartbeats. `0` turns it off |
| `LEAK_MB_PER_BEAT` | `0` | Extra memory to hold on each heartbeat, in MB. `0` turns it off |

## Requirements

- Linux with systemd running as PID 1. Tested on Ubuntu 22.04 on WSL2, with systemd 249 and Python 3.10.
- Python 3 at `/usr/bin/python3`. The app only uses the standard library.
- `sudo` access.

On WSL, systemd must be turned on in `/etc/wsl.conf`:

```ini
[boot]
systemd=true
```

## Setup

Run these from the project folder.

```bash
# Create the non-root service user
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin testpress

# Install the app, settings and unit file
sudo mkdir -p /opt/testpress-worker
sudo cp app.py /opt/testpress-worker/app.py
sudo cp testpress-worker.env /etc/testpress-worker.env
sudo cp testpress-worker.service /etc/systemd/system/testpress-worker.service

# Load the unit file, start the service now, and start it at every boot
sudo systemctl daemon-reload
sudo systemctl enable --now testpress-worker
```

The app goes in `/opt` because the `testpress` user can't read a normal user's home folder.

## Check that it works

```bash
systemctl status testpress-worker --no-pager -l
journalctl -u testpress-worker -f
ps -o user,pid,ppid,stat,cmd -p $(pgrep -f app.py)
```

The status should show `active (running)`, and `ps` should show the `testpress` user (possibly shortened to `testpre+`) with PPID `1`. Press `Ctrl+C` to stop following the logs. This doesn't stop the service.

## Running the app without systemd

```bash
python3 app.py
CRASH_AFTER=3 python3 app.py
HEARTBEAT_INTERVAL=1 python3 app.py
```

## Reproducing the experiments

Stop any copy of the app you started by hand first, because `pgrep -f app.py` matches every copy. Reset the service after each experiment, using the steps in [Resetting the service](#resetting-the-service).

| Experiment | How to run it | What to expect |
|---|---|---|
| SIGTERM | `sudo kill -TERM $(pgrep -f app.py)` | Clean exit, `Deactivated successfully`, no restart |
| SIGKILL | `sudo kill -9 $(pgrep -f app.py)` | `status=9/KILL`, restart after 5 seconds with a new PID |
| Non-zero exit | Set `CRASH_AFTER=3`, then restart | `status=1/FAILURE`, restarts about every 15 seconds |
| Repeated crashes | Set `CRASH_AFTER=1`, then restart | `Start request repeated too quickly`, then `failed` |
| Invalid executable path | Change `ExecStart=` to a wrong path, then run `daemon-reload` and restart | `status=203/EXEC`, then `failed` after retries |
| Memory limit | Set `LEAK_MB_PER_BEAT=10`, then restart | OOM kill, `status=9/KILL`, `Failed with result 'oom-kill'` |
| Reboot | Reboot the machine. On WSL, run `wsl --shutdown` in PowerShell and reopen the distro | Service is `active (running)` without being started by hand |

To change a setting and restart:

```bash
sudo sed -i 's/^CRASH_AFTER=.*/CRASH_AFTER=3/' /etc/testpress-worker.env
sudo systemctl restart testpress-worker
```

To break the path:

```bash
sudo sed -i 's#^ExecStart=.*#ExecStart=/usr/bin/python3-wrong /opt/testpress-worker/app.py#' /etc/systemd/system/testpress-worker.service
sudo systemctl daemon-reload
sudo systemctl restart testpress-worker
```

## Resetting the service

Run these from the project folder. They restore the original files and clear the rate limit.

```bash
sudo cp testpress-worker.env /etc/testpress-worker.env
sudo cp testpress-worker.service /etc/systemd/system/testpress-worker.service
sudo systemctl daemon-reload
sudo systemctl reset-failed testpress-worker
sudo systemctl restart testpress-worker
```

## Diagnosing a failure

```bash
systemctl status testpress-worker --no-pager -l
journalctl -u testpress-worker -n 50 --no-pager
systemctl show testpress-worker -p NRestarts -p Result -p ExecMainStatus
systemd-analyze verify /etc/systemd/system/testpress-worker.service
sudo -u testpress /usr/bin/python3 /opt/testpress-worker/app.py
```

The exit status tells you where to look first:

| Status | Likely cause | Where to look |
|---|---|---|
| `203/EXEC` | systemd couldn't run the program | The `ExecStart=` path |
| `1/FAILURE` | The app exited with an error | The traceback in the journal |
| `9/KILL` | Something killed the process | The journal, and whether it says `oom-kill` |

## Key settings in the unit file

| Setting | What it does |
|---|---|
| `Restart=on-failure`, `RestartSec=5` | Restarts 5 seconds after a failure, but not after a clean exit |
| `StartLimitBurst=5`, `StartLimitIntervalSec=60` | Allows 5 starts in 60 seconds, then stops trying, so a broken service doesn't retry forever |
| `TimeoutStopSec=30` | Waits up to 30 seconds after SIGTERM, then uses SIGKILL |
| `MemoryMax=50M`, `MemorySwapMax=0` | Limits memory to 50 MB with no swap |
| `CPUQuota=20%` | Limits CPU to 20% of one core |
| `WantedBy=multi-user.target` | Starts the service at boot, once it's enabled |

## WSL notes

- WSL boots when it's opened, not when Windows starts. The service starts as soon as the distro boots.
- If you have more than one distro, open the one the service is installed on, for example `wsl -d Ubuntu-22.04`.

## Removing everything

```bash
sudo systemctl disable --now testpress-worker
sudo rm /etc/systemd/system/testpress-worker.service /etc/testpress-worker.env
sudo rm -r /opt/testpress-worker
sudo systemctl daemon-reload
sudo userdel testpress
```
