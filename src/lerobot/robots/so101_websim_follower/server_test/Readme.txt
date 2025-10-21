Calibration saved to /home/math/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/blue.json
INFO 2025-10-18 17:17:51 1_leader.py:156 blue SO101Leader disconnected.



lerobot-calibrate     --teleop.type=so101_leader     --teleop.port=/dev/ttyACM0 --teleop.id=blue



to test:
python sim_ws_server.py


lerobot-teleoperate \
  --robot.type=so101_websim_follower \
  --robot.ws_url=ws://127.0.0.1:8765 \
  --teleop.type=so101_leader \
  --teleop.port=/dev/ttyACM0 \
  --teleop.id=blue \
  --display_data=false
