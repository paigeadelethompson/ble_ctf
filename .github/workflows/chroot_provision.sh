#!/bin/bash
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update || true
apt-get install -y --no-install-recommends software-properties-common ca-certificates apt-transport-https lsb-release || true
if command -v add-apt-repository >/dev/null 2>&1; then
  add-apt-repository -y universe || true
else
  CODENAME=$(lsb_release -cs || echo jammy)
  echo "deb http://archive.ubuntu.com/ubuntu/ ${CODENAME} universe" >> /etc/apt/sources.list || true
fi
apt-get update || true

# Install kernel, grub (BIOS), python3-pip and other userland packages
apt-get install -y --no-install-recommends linux-image-generic grub-pc openssh-server sudo cloud-init curl ca-certificates python3-pip python-is-python3 python3-venv python3-distutils git || true

# Generate initramfs for installed kernels
update-initramfs -u -k all || true

# Install grub onto the attached block device (device visible as /dev/nbd0 inside chroot)
grub-install --target=i386-pc --recheck /dev/nbd0 || true
update-grub || true

# Vagrant user + SSH key
useradd -m -s /bin/bash vagrant || true; echo 'vagrant:vagrant' | chpasswd || true
mkdir -p /home/vagrant/.ssh; curl -sL https://raw.githubusercontent.com/hashicorp/vagrant/master/keys/vagrant.pub -o /home/vagrant/.ssh/authorized_keys || true
chmod 0700 /home/vagrant/.ssh; chmod 0600 /home/vagrant/.ssh/authorized_keys; chown -R vagrant:vagrant /home/vagrant/.ssh || true
echo 'vagrant ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/vagrant; chmod 0440 /etc/sudoers.d/vagrant || true

apt-get clean || true

# Install Ansible from apt (prefer distro package over pip in chroot)
apt-get update || true
apt-get install -y --no-install-recommends ansible || true
if [ -f /vagrant/tools/ansible/playbook.yml ]; then
  ansible-playbook -i 'localhost,' -c local /vagrant/tools/ansible/playbook.yml --become --diff || true
else
  echo 'No playbook found at /vagrant/tools/ansible/playbook.yml; skipping ansible.'
fi
