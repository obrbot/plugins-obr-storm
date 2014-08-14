import asyncio
import re
from decimal import Decimal, InvalidOperation

import requests

from obrbot import hook
from obrbot.util.dictionaries import CaseInsensitiveDict

plugin_info = {
    "plugin_category": "channel-specific",
    "command_category_name": "DogeStorm"
}

url = "http://coinmill.com/frame.js"
currency_rates = CaseInsensitiveDict()
currency_units = CaseInsensitiveDict()  # this will be ignored, at least for now


@asyncio.coroutine
@hook.on_start()
def load_rates():
    regex = re.compile(r"var currency_data=\'([0-9a-zA-Z,\.\|\-]+)\';")
    response = requests.get(url)
    match = regex.match(response.text)
    if not match:
        raise ValueError("Unmatched data: {} Please update!".format(response.text))
    data = match.group(1)
    assert isinstance(data, str)  # for pycharm
    for currency_str in data.split('|'):
        currency_split = currency_str.split(',')
        if len(currency_split) != 3:
            raise ValueError("Invalid currency split {}!".format(currency_str))
        symbol = currency_split[0]
        try:
            rate = Decimal(currency_split[1])
        except InvalidOperation:
            raise ValueError("Invalid decimal '{}'".format(currency_split[1]))
        try:
            unit = Decimal(currency_split[2])
        except InvalidOperation:
            raise ValueError("Invalid decimal '{}'".format(currency_split[2]))
        currency_rates[symbol] = rate
        currency_units[symbol] = unit


@hook.regex("^.convert ?(.*)$")  # Until I add support for per-plugin prefixes
@hook.command('convert')
def convert_command(event):
    if hasattr(event, "match"):
        prefix = '.'
        text = event.match.group(1)
    else:
        prefix = event.conn.config.get('prefix')
        text = event.text
    split = text.split()
    if len(split) != 3:
        event.message("Usage: {}convert <FROM> <TO> <AMOUNT>".format(prefix))
        return

    from_currency = split[0]
    to_currency = split[1]
    try:
        amount = Decimal(split[2])
    except InvalidOperation:
        event.message("Invalid amount '{}'".format(split[2]))
        return

    if from_currency not in currency_rates:
        event.message("Unknown currency '{}'".format(from_currency))
        return
    if to_currency not in currency_rates:
        event.message("Unknown currency '{}'".format(to_currency))
        return

    result = amount * currency_rates[from_currency] / currency_rates[to_currency]
    result = round(result.__round__, 5).normalize()

    event.message("{} {} to {} = {}".format(str(amount), from_currency.lower(), to_currency.lower(), result))
