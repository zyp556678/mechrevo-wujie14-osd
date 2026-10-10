"""Poll MIFS features and emit an OSD request when a value changes.

The firmware exposes state, not events: there is no queue and no counter, so
a change can only be observed by sampling. That means a fast double-press can
be missed entirely. The debounce step below does not fix that, but it does
stop us showing a value the hardware has already moved past.

Timing: POLL_INTERVAL is short enough that a deliberate key press is caught
well within human reaction time. After a change we wait DEBOUNCE_DELAY and
read again, so a value that is still settling is not reported twice.
"""
import time

from . import acpi, features, mapper

POLL_INTERVAL = 0.3
DEBOUNCE_DELAY = 0.15


class Poller:
    """Samples polled features and reports changes via a callback.

    The callback receives (feature, value, icon_filename).
    """

    def __init__(self, on_change):
        self._on_change = on_change
        self._last = {}

    def prime(self):
        """Record current values without reporting them.

        Called at startup so the first poll does not announce the state the
        machine was already in.
        """
        for name in features.POLLED:
            self._last[name] = acpi.get(name)

    def poll_once(self):
        """Sample every feature once and report any that changed."""
        for name in features.POLLED:
            value = acpi.get(name)
            if value is None:
                continue
            if self._last.get(name) == value:
                continue
            # The value may still be moving (fast repeat presses land inside
            # this window). Re-read and report where it settled, not the
            # transient we happened to catch first.
            time.sleep(DEBOUNCE_DELAY)
            confirmed = acpi.get(name)
            if confirmed is None:
                continue
            self._last[name] = confirmed
            self._report(name, confirmed)

    def _report(self, name, value):
        icon = mapper.icon_for(name, value)
        if icon is None:
            return
        self._on_change(name, value, icon)

    def run(self, should_stop):
        """Poll until should_stop() returns True."""
        while not should_stop():
            try:
                self.poll_once()
            except acpi.AcpiError:
                # Transient failure (module unloaded, EC busy); keep going.
                pass
            time.sleep(POLL_INTERVAL)
