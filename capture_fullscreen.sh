#!/bin/bash
# Script to capture full-screen dialog screenshots

# Run the app with debug-svg, send F2 after 1 second, then ESC after another second
(
  sleep 1
  # Send F2 to trigger login dialog
  xdotool key F2
  sleep 1
  # Send ESC to close
  xdotool key Escape
  sleep 0.5
  # Send F12 for shutdown dialog
  xdotool key F12
  sleep 1
  # Send ESC to close
  xdotool key Escape
  sleep 0.5
  # Kill the app
  pkill -f "uv run zboxtui"
) &

# Run the app
uv run zboxtui --debug-svg
