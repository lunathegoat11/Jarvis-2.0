"""Jarvis Nano: Jarvis in a robot body.

The robot (robot/body_server.py on its Raspberry Pi) is the body: wheels,
claw, LED eyes, camera, microphone and speaker. This package is the mind. It
runs on a computer on the same Wi-Fi, listens to the robot's microphone for
"Hey Jarvis", thinks with the same brain, memory and learning as Jarvis, and
answers through the robot's speaker. Desktop tools (screen, browser,
calendar, keyboard) are left out; robot tools take their place.

Start it with:  python -m jarvis.nano
"""
