"""core/ssh.py — SSH connections via Paramiko"""
import paramiko
import socket
import threading


class SSHSession:
    def __init__(self):
        self.client   = None
        self.shell    = None
        self.connected = False

    def connect(self, host, port=22, username="admin", password=""):
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                host, port=int(port), username=username,
                password=password, timeout=10, look_for_keys=False,
            )
            self.connected = True
            return True, "Connected"
        except Exception as e:
            return False, str(e)

    def run(self, command):
        if not self.connected:
            return False, "Not connected"
        try:
            _, stdout, stderr = self.client.exec_command(command, timeout=30)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            return True, out + err
        except Exception as e:
            return False, str(e)

    def disconnect(self):
        if self.client:
            self.client.close()
        self.connected = False


# VPS session (singleton)
_vps_session = SSHSession()


def vps_run(command, host, username, password, port=22):
    """Run a command on the VPS, reusing connection if alive."""
    global _vps_session
    if not _vps_session.connected:
        ok, msg = _vps_session.connect(host, port, username, password)
        if not ok:
            return False, f"VPS connect failed: {msg}"
    return _vps_session.run(command)


def quick_ssh(host, port, username, password, command):
    """One-shot SSH command, new connection each time."""
    sess = SSHSession()
    ok, msg = sess.connect(host, port, username, password)
    if not ok:
        return False, msg
    result = sess.run(command)
    sess.disconnect()
    return result
