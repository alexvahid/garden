source gardenenv/bin/activate
cd /home/pi/garden
git pull --timeout=5 2>/dev/null || true
cp ./bash_profile.sh ~/.bash_profile
python3 /home/pi/garden/garden.py &