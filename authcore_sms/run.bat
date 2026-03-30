@echo off
echo Installing required packages...
pip install -r requirements.txt

echo Starting AuthCore Application...
python app.py

pause