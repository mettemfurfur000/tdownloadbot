#!/bin/bash

# make sure to keep bot alive for some time

mkdir downloads

screen -dmS telegram_yt_bot bash -c "python bot.py"