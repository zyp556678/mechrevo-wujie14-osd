#!/bin/bash
# End-to-end test as root, on a private session bus.
#
# root cannot join the desktop user's session bus (its security policy
# rejects the connection), so dbus-run-session creates a throwaway bus that
# both the daemon and the subscriber can use. This exercises acpi -> poller
# -> mapper -> D-Bus signal -> subscriber, which is everything except the
# shell extension.
set -eu

exec dbus-run-session -- /usr/bin/python3 -I -u \
    /home/wuxianjinbu/WorkSpace/ShareSpace/OSD_V06/tools/e2etest.py "${1:-60}"
