source gardenenv/bin/activate
cd /home/pi/garden
git pull
cp ./bash_profile.sh ~/.bash_profile
python3 /home/pi/garden/garden.py &