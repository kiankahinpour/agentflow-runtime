#!/bin/sh
# Requires operator-supplied legitimate Debian cloud qcow2 and libguestfs.
# No network downloads or credentials are embedded in the build script.
set -eu
if [ "$#" -ne 2 ]; then echo "usage: guest/build_guest.sh trusted-debian-cloud.qcow2 output.qcow2" >&2;exit 2;fi
command -v qemu-img >/dev/null || { echo "qemu-img missing" >&2;exit 2; }
command -v virt-customize >/dev/null || { echo "virt-customize missing" >&2;exit 2; }
SOURCE=$1;OUTPUT=$2
[ -f "$SOURCE" ] && [ ! -e "$OUTPUT" ] || { echo "missing source or output exists" >&2;exit 2; }
qemu-img convert -f qcow2 -O qcow2 "$SOURCE" "$OUTPUT"
virt-customize -a "$OUTPUT" \
  --run-command 'id agentflow >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin agentflow' \
  --mkdir /opt/agentflow \
  --upload guest/agentflow_guest.py:/opt/agentflow/agentflow_guest.py \
  --upload guest/agentflow-guest.service:/etc/systemd/system/agentflow-guest.service \
  --run-command 'chown -R root:root /opt/agentflow; chmod 755 /opt/agentflow/agentflow_guest.py' \
  --run-command 'systemctl enable agentflow-guest.service' \
  --run-command 'systemctl mask serial-getty@ttyS0.service || true' \
  --run-command 'systemctl disable ssh || true' \
  --run-command 'systemctl disable cloud-init || true'
sha256sum "$OUTPUT"
echo "Review guest image, first-boot state, and console output before handling untrusted prompts."
