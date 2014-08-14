import asyncio
import re

import requests

from obrbot import hook

plugin_info = {
    "plugin_category": "channel-specific",
    "command_category_name": "DogeStorm"
}

url = "http://coinmill.com/frame.js"
currency_rates = {}


@asyncio.coroutine
@hook.on_start()
def load_rates():
    regex = re.compile(r"var currency_data=\'([0-9a-zA-Z,\.\|\-]+)\';")
    result = requests.get(url)
    match = regex.match(result.text)
    if not match:
        raise ValueError("Unmatched data: {}".format(result.text))
    data = match.group(1)
