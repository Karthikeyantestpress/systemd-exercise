# Experiments

## 1. Running process
- **Evidence:** `evidence/01-running-process.png`
- **Action:** Ran `python3 app.py` in terminal 1. In terminal 2, ran
  `pgrep -af app.py` and `ps -o pid,ppid,stat,cmd -p $(pgrep -f app.py)`.
- **Expectation:** I expected to see one Python process with a PID, sleeping
  most of the time because the program waits between heartbeats.
- **Observation:** `pgrep` showed one process with PID `5328`. `ps` showed
  PPID `372` and state `S+`.
- **Explanation:** Running the program created a new process, and Linux gave it
  a PID. Bash started it, so bash is its parent. The state is `S` because the
  program spends most of its time in `time.sleep()`, and `+` means it's in the
  foreground of the terminal.

## 2. Graceful shutdown (SIGTERM)
- **Evidence:** `evidence/02-graceful-shutdown.png`
- **Action:** Ran `python3 app.py` in terminal 1. In terminal 2, ran
  `kill -TERM $(pgrep -f app.py)`. Then ran `echo $?` in terminal 1.
- **Expectation:** I expected the program to log that it received SIGTERM,
  finish its current work, and exit cleanly.
- **Observation:** The log showed `Received SIGTERM. Finishing current work...`
  at `2026-11-05 08:49:53`, then `Shutdown complete. Exiting cleanly.` at `2026-11-05 08:49:57`.
  The exit code was `0`.
- **Explanation:** SIGTERM is a polite request to stop, and a program can handle
  it. My handler set `running = False`, so the current sleep finished, the loop
  ended, and the program exited by itself. The exit code is `0` because the
  program finished normally. The delay depends on how much of the sleep was left.

## 3. Forced termination (SIGKILL)
- **Evidence:** `evidence/03-forced-termination.png`
- **Action:** Ran `python3 app.py` in terminal 1. In terminal 2, ran
  `kill -9 $(pgrep -f app.py)`. Then ran `echo $?` in terminal 1.
- **Expectation:** I expected the process to stop immediately with no
  shutdown message.
- **Observation:** The terminal printed `Killed`. No shutdown log
  appeared. The exit code was `137`.
- **Explanation:** SIGKILL can't be caught or handled, so the kernel ended the
  process immediately and my handler never ran. That's why there was no chance
  to clean up. The exit code is `137`, which is 128 + 9 (the SIGKILL number).

## 4. systemd service
- **Evidence:** `evidence/04-systemd-service.png`
- **Action:** Created the `testpress` user and copied the app, environment file
  and unit file into place. Then ran `sudo systemctl daemon-reload`,
  `sudo systemctl enable --now testpress-worker` and
  `systemctl status testpress-worker --no-pager`. Checked the process with
  `ps -o user,pid,ppid,stat,cmd -p $(pgrep -f app.py)`.
- **Expectation:** I expected the service to start without a terminal, run as
  the `testpress` user, and be enabled to start at boot.
- **Observation:** Status showed `enabled` and `active (running)` with Main PID
  `6964`. `ps` showed user `testpre+` (`testpress` shortened), PPID `1` and state
  `Ss`. Heartbeats appeared in `journalctl -u testpress-worker`.
- **Explanation:** systemd read the unit file and started the program as the
  user set in `User=`, so it doesn't run as root. PPID is `1` because systemd
  (PID 1) started it directly, not my bash. There's no `+` in the state because
  it isn't attached to a terminal, so closing my terminals doesn't affect it.
  `enable` set it to start at boot, and journald collects its output.

## 5. Automatic restart
- **Evidence:** `evidence/05-automatic-restart.png`
- **Action:** Ran `pgrep -af app.py`, then `sudo kill -9 $(pgrep -f app.py)`,
  then `systemctl status testpress-worker --no-pager` and `pgrep -af app.py` again.
- **Expectation:** I expected systemd to restart it, because the process was killed unexpectedly.
- **Observation:** The PID changed from `7400` to `7419`. The journal showed
  `code=killed, status=9/KILL`, `Failed with result 'signal'` and
  `restart counter is at 1`. The restart came 5 seconds after the kill.
- **Explanation:** SIGKILL can't be handled, so the process died immediately.
  systemd treated that as a failure, and `Restart=on-failure` with `RestartSec=5`
  started a new process after 5 seconds. The PID changed because it's a new process.

## 5b. SIGTERM under systemd
- **Evidence:** the journal in `evidence/05-automatic-restart.png`
- **Action:** Ran `sudo kill -TERM $(pgrep -f app.py)` and checked the status.
- **Expectation:** I expected systemd to restart it, because the process stopped.
- **Observation:** The app logged `Received SIGTERM` and `Shutdown complete`.
  systemd logged `Deactivated successfully` and didn't restart it.
- **Explanation:** The handler let the app exit cleanly with code `0`. systemd saw
  a clean stop, and `Restart=on-failure` doesn't restart after one.

## 6. Crash investigation (non-zero exit)
- **Evidence:** `evidence/06-crash-investigation.png`
- **Action:** Set `CRASH_AFTER=3` in `/etc/testpress-worker.env`, ran
  `sudo systemctl restart testpress-worker`, then read the logs with
  `journalctl -u testpress-worker -n 40 --no-pager`.
- **Expectation:** I expected the app to crash after 3 heartbeats and systemd to restart it, because `Restart=on-failure` covers non-zero exits.
- **Observation:** The journal showed `RuntimeError: Simulated crash`,
  `status=1/FAILURE` and `Failed with result 'exit-code'`. A new PID started
  each time, and the restart counter went up. It crashed about every 15 seconds.
- **Explanation:** The uncaught error made Python exit with code `1`. systemd
  treats that as a failure, so `Restart=on-failure` restarted it. It stayed under
  the rate limit, with about 4 starts per minute, so it kept restarting.

## 7. Invalid configuration
- **Evidence:** `evidence/07-invalid-configuration.png`
- **Action:** Changed `ExecStart=` to `/usr/bin/python3-wrong`, ran
  `sudo systemctl daemon-reload` and `sudo systemctl restart testpress-worker`,
  then checked `systemctl status` and `journalctl`.
- **Expectation:** I expected an error, because the file path is invalid.
- **Observation:** The journal showed `Failed to locate executable
  /usr/bin/python3-wrong: No such file or directory` and `status=203/EXEC`.
  No app logs appeared. systemd retried, then the service ended up failed.
- **Explanation:** systemd couldn't find the program, so my Python code never ran.
  `203/EXEC` is systemd's code for that. It counts as a failure, so it retried until
  it hit the rate limit. Retrying can't fix a wrong path, so I had to correct the file.

## 8. Repeated crashes (rate limiting)
- **Evidence:** `evidence/08-repeated-crashes.png`
- **Action:** Set `CRASH_AFTER=1`, restarted the service, then checked
  `systemctl status` and `journalctl`.
- **Expectation:** I expected systemd to stop restarting after 5 starts in 60 seconds, because of `StartLimitBurst=5` and `StartLimitIntervalSec=60`.
- **Observation:** It crashed about every 5 seconds. At `09:38:33` the journal
  showed `Start request repeated too quickly` and `Failed to start`.
- **Explanation:** `StartLimitBurst=5` and `StartLimitIntervalSec=60` allow 5
  starts in 60 seconds. The next start was refused and the service stayed failed.
  This stops endless restarts, so a person has to investigate.

## 9. Resource limits
- **Evidence:** `evidence/09-resource-limits.png`
- **Action:** Set `MemoryMax=50M`, `MemorySwapMax=0` and `CPUQuota=20%` in the unit
  file. Set `LEAK_MB_PER_BEAT=10` and restarted the service, then read `journalctl`.
- **Expectation:** I expected it to fail once it reached the limit.
- **Observation:** `systemctl show` reported `MemoryMax=52428800` (50 MB),
  `MemorySwapMax=0` and `CPUQuotaPerSecUSec=200ms` (20% of one core). The log
  reached `Holding 40 MB`, then showed `killed by the OOM killer`,
  `code=killed, status=9/KILL` and `Failed with result 'oom-kill'`. A new process,
  PID `9233`, started about 5 seconds later and began leaking again.
- **Explanation:** systemd applies these limits using cgroups. Python itself also
  uses memory, so the process hit 50 MB before holding 50 MB of extra data. The
  kernel's OOM killer ended it with SIGKILL, so my handler couldn't run. systemd
  treated that as a failure and restarted it, but a restart doesn't fix a leak.

## 10. Reboot persistence
- **Evidence:** `evidence/10-reboot-persistence.png`
- **Action:** Ran `wsl --shutdown` from PowerShell, reopened Ubuntu, then ran
  `uptime -s`, `systemctl status testpress-worker --no-pager -l` and
  `journalctl --list-boots --no-pager`.
- **Expectation:** I expected it to start automatically after the reboot, because I enabled it.
- **Observation:** The boot list showed the previous boot ended at `10:06:29`.
  `uptime -s` showed the new boot at `10:09:04`. The service was `active (running)`
  since `10:09:25`, with PID `276` (it was `283` in the previous boot), and I didn't
  start it myself. Reopening WSL first showed the error `Wsl/Service/E_UNEXPECTED`,
  and WSL then came back up.
- **Explanation:** `systemctl enable` linked the service to `multi-user.target`, so
  systemd started it during boot. The PID changed because it's a new process.
  On WSL, the VM boots when it's opened, but the service still starts by itself.

## How I investigate a service that keeps crashing
1. `systemctl status testpress-worker --no-pager -l`: see the state and exit status.
2. `journalctl -u testpress-worker -n 50 --no-pager`: find the first real error.
3. `systemctl show testpress-worker -p NRestarts -p Result -p ExecMainStatus`:
   see how often it restarted and how it ended.
4. Use the exit status to decide where to look: `203` means the `ExecStart=` path,
   `1` means the app's traceback, and `9/KILL` means something killed it.
5. `systemd-analyze verify /etc/systemd/system/testpress-worker.service`: check the unit file for mistakes.
6. `sudo -u testpress /usr/bin/python3 /opt/testpress-worker/app.py`: run it by hand
   as the service user.
7. Fix the cause, then run `sudo systemctl reset-failed testpress-worker` and
   `sudo systemctl start testpress-worker`.
