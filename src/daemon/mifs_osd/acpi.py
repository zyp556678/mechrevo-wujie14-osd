"""MIFS protocol: talk to the ACPI WMAA dispatcher through acpi_call.

The interface is a fixed 32-byte buffer exchanged with

    \\_SB.PCI0.WMID.WMAA 0x0 0x0 {32 bytes}

Byte layout (verified against the firmware AML and by live probing):

    [1]  0xFA = Get, 0xFB = Set
    [3]  feature name
    [4]  value (Set only)

The reply uses the same layout: [1] is 0x80 on success, [3] echoes the
feature name, [4] carries the value.

The call string is built from integers only. Nothing caller-supplied is ever
interpolated into it, so a feature name or value can never inject AML.
"""
import os
import re
import subprocess

from . import features

ACPI_CALL = '/proc/acpi/call'
ACPI_PATH = r'\_SB.PCI0.WMID.WMAA'
BUF_LEN = 32
STATUS_OK = 0x80

# Reply looks like "{0x00, 0x80, 0x00, 0x08, ...}" or "Error: AE_..."
_BUF_RE = re.compile(r'\{([^}]*)\}')


class AcpiError(RuntimeError):
    """The ACPI call failed or returned something unparseable."""


class AcpiUnavailable(AcpiError):
    """acpi_call is not loaded, so /proc/acpi/call is missing."""


def _build_call(buf):
    """Render the 32-byte buffer as an acpi_call command line."""
    body = ', '.join('0x%02x' % b for b in buf)
    return '%s 0x0 0x0 {%s}' % (ACPI_PATH, body)


def _parse_reply(text):
    """Extract the returned byte buffer from acpi_call's output."""
    text = text.strip()
    m = _BUF_RE.search(text)
    if not m:
        raise AcpiError('no buffer in reply: %r' % text)
    out = bytearray(BUF_LEN)
    parts = [p.strip() for p in m.group(1).split(',') if p.strip()]
    for i, p in enumerate(parts):
        if i >= BUF_LEN:
            break
        try:
            out[i] = int(p, 0) & 0xFF
        except ValueError:
            raise AcpiError('bad byte %r in reply' % p)
    return bytes(out)


def _write_call(cmd):
    """Run one acpi_call and return the raw reply text."""
    if not os.path.exists(ACPI_CALL):
        raise AcpiUnavailable('%s missing; is acpi_call loaded?' % ACPI_CALL)
    try:
        with open(ACPI_CALL, 'w') as f:
            f.write(cmd)
        with open(ACPI_CALL, 'r') as f:
            return f.read()
    except PermissionError:
        raise AcpiError('%s is root-only; run as root' % ACPI_CALL)


def call(buf):
    """Send a 32-byte buffer and return the 32-byte reply."""
    if len(buf) != BUF_LEN:
        raise ValueError('buffer must be %d bytes' % BUF_LEN)
    reply = _parse_reply(_write_call(_build_call(buf)))
    if reply[1] != STATUS_OK:
        raise AcpiError('status 0x%02x (not 0x%02x) for feature 0x%02x'
                        % (reply[1], STATUS_OK, buf[3]))
    return reply


def get(name):
    """Read a feature's current value. Returns an int, or None if unsupported."""
    code = features.POLLED[name]
    buf = bytearray(BUF_LEN)
    buf[1] = features.GET
    buf[3] = code
    try:
        return call(bytes(buf))[4]
    except AcpiError:
        return None


def set_value(name, value):
    """Write a feature value. Returns True on success."""
    lo, hi = features.VALUE_RANGE[name]
    value = int(value)
    if not lo <= value <= hi:
        raise ValueError('%s out of range %d..%d: %d' % (name, lo, hi, value))
    code = features.POLLED[name]
    buf = bytearray(BUF_LEN)
    buf[1] = features.SET
    buf[3] = code
    buf[4] = value
    try:
        call(bytes(buf))
        return True
    except AcpiError:
        return False


def module_loaded():
    """True when acpi_call is loaded and /proc/acpi/call is writable."""
    return os.path.exists(ACPI_CALL) and os.access(ACPI_CALL, os.W_OK)


def load_module():
    """Best-effort modprobe of acpi_call. Returns True if it is loaded after."""
    if module_loaded():
        return True
    try:
        subprocess.run(['/usr/sbin/modprobe', 'acpi_call'],
                       check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass
    return module_loaded()
