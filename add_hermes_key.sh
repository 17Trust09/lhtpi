#!/bin/bash
# Von Tim auf dem Pi auszuführen:
# sh /home/pi/add_hermes_key.sh

mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKFMt9FKnyzlN6pix6Vd91wNry3iWJRt/41YPw0YuxZJ yuuki-hermes-agent" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "✅ Hermes SSH-Key hinzugefügt"
