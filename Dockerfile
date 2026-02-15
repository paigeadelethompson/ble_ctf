FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install essentials and Python3/pip

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    sudo git python-is-python3 python3-pip python3-setuptools \
    build-essential ca-certificates ssh \
    curl gnupg2 apt-transport-https \
 && rm -rf /var/lib/apt/lists/*

# Create vagrant user (playbook expects /home/vagrant)

RUN useradd -m -s /bin/bash vagrant \
 && echo 'vagrant ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/vagrant

# Upgrade pip/setuptools/wheel and install Ansible via pip

RUN pip3 install --upgrade pip setuptools wheel \
 && pip3 install --no-cache-dir ansible

# Copy repository into image

WORKDIR /vagrant

COPY . /vagrant

# Ensure the vagrant user owns the mounted project directory

RUN chown -R vagrant:vagrant /vagrant

# Set HOME for vagrant user

ENV HOME=/home/vagrant

# Run the Ansible playbook to provision system packages and build native components
# The playbook will install required apt packages and create /home/vagrant/src, then
# run Poetry creation as the vagrant user.

RUN ansible-playbook -i 'localhost,' -c local tools/ansible/playbook.yml --become --diff

WORKDIR /home/vagrant

USER vagrant

CMD ["/bin/bash"]
