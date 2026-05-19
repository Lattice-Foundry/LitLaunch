"""Minimal Streamlit app for LitLaunch smoke checks."""

from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="LitLaunch Example App", layout="centered")

st.title("LitLaunch Example App")
st.write(
    "If you can see this page, LitLaunch successfully launched a Streamlit runtime."
)

st.subheader("Runtime")
st.write(f"Python: `{sys.version.split()[0]}`")
st.write(f"Platform: `{platform.platform()}`")
st.write(f"Working directory: `{Path.cwd()}`")
st.write(f"UTC time: `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`")

query_params = dict(st.query_params)
if query_params:
    st.subheader("Query Parameters")
    st.json(query_params)

st.divider()
st.markdown(
    "[LitLaunch](https://github.com/LatticeFoundry/litlaunch) is built by "
    "[LatticeFoundry](https://github.com/LatticeFoundry), a software division "
    "of Sierra Cognitive Group, LLC. "
    "[RoleThread](https://github.com/LatticeFoundry/rolethread) is part of the "
    "same local-first ecosystem."
)
