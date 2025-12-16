import os
import subprocess
import signal
import time

PORTS = [8000, 8001, 8002, 8501]

def get_pids(port):
    """Returns a list of PIDs using the specified port."""
    pids = set()
    try:
        # Try lsof
        output = subprocess.check_output(f"lsof -t -i:{port}", shell=True, stderr=subprocess.DEVNULL)
        for pid in output.decode().split():
            pids.add(int(pid))
    except Exception:
        pass
        
    try:
        # Try netstat if lsof failed or returned nothing
        output = subprocess.check_output(f"netstat -nlp | grep :{port}", shell=True, stderr=subprocess.DEVNULL)
        for line in output.decode().splitlines():
            parts = line.split()
            for part in parts:
                if '/' in part and part.split('/')[0].isdigit():
                    pids.add(int(part.split('/')[0]))
    except Exception:
        pass
        
    return list(pids)

def kill_pids(pids):
    for pid in pids:
        try:
            print(f"Killing PID {pid}...")
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"Error killing {pid}: {e}")

def main():
    print(">>> Aggressive Port Cleanup Started...")
    for port in PORTS:
        pids = get_pids(port)
        if pids:
            print(f"Found processes on port {port}: {pids}")
            kill_pids(pids)
        else:
            print(f"Port {port} is free.")
    print(">>> Cleanup Complete.")

if __name__ == "__main__":
    main()