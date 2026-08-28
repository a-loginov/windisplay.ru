import json
import os
import re
import time
import uuid
from datetime import datetime, date, timedelta
from difflib import SequenceMatcher

import requests
from flask import jsonify, request, render_template, Response, stream_with_context
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.orm.attributes import flag_modified
from main import app, config


# Инцилизация AI_Agent Timeweb #
OPENAI_URL=os.environ["OPENAI_URL"]
ASSET_ID=os.environ["ASSET_ID"]
API_KEY=os.environ["API_KEY"]




# ---------------------------------------- SYSTEM_PROMT ---------------------------------------- #



