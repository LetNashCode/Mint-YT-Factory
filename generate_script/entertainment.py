"""Entertainment-first storyboard generator for Mint-YT-Factory."""
from __future__ import annotations

import json
import os
import re
import time
import uuid

from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.5-flash-lite"
MODEL_FALLBACKS = ("gemini-2.5-flash-lite", "gemini-3.6-flash")
SCENE_COUNT = 7
VISUALS_PER_SCENE = 2
SCENE_DURATIONS = [3, 5, 7, 7, 8, 8, 7]
MAX_ATTEMPTS = 4

# The remainder of this module is intentionally kept identical to the existing
# entertainment generator.  Only the model selection and request retry path are
# hardened below; the existing schemas, prompts, normalization and validation
# remain authoritative.
