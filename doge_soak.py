import asyncio
import logging
import random

from obrbot import hook

pending_soaks = []

doge_nick = 'DogeWallet'
max_doge = 500

logger = logging.getLogger('obrbot')


@asyncio.coroutine
def get_raw_balance(event):
    """
    :type event: obrbot.event.Event
    """
    result = yield from event.async(event.db.get, 'plugins:doge-wallet:balance')
    if result is None:
        return 0
    else:
        return float(result)


@asyncio.coroutine
def thanked_timer(event, nick):
    """
    :type event: obrbot.event.Event
    """
    result = yield from event.async(event.db.get)


@asyncio.coroutine
def get_active(event):
    """
    :type event: obrbot.event.Event
    """
    event.message("active", target="DogeWallet")
    active = (yield from event.wait_for_message("Active Shibes: ([0-9]*)", nick="DogeWallet")).group(1)

    print("Active: " + active)
    return int(active)


# this can be used as a command, or just as a function
@asyncio.coroutine
@hook.command("update-balance", autohelp=False)
def update_balance(event):
    """
    :type event: obrbot.event.Event
    """
    stored_balance = yield from get_raw_balance(event)

    event.message("balance", target="DogeWallet")
    balance = float((yield from event.wait_for_message("([0-9]*\.?[0-9]*)", nick="DogeWallet")).group(1))

    if stored_balance != balance:
        yield from event.async(event.db.set, 'plugins:doge-wallet:balance', balance)

    return balance


@asyncio.coroutine
def add_doge(event, amount_added):
    """
    :type event: obrbot.event.Event
    """
    balance = float((yield from event.async(event.db.incrbyfloat, 'plugins:doge-wallet:balance', amount_added)))
    if balance > max_doge:
        active = yield from get_active(event)
        if active < 1:
            return

        balance = yield from update_balance(event)

        event.message(".soak {}".format(balance / active))
        yield from update_balance(event)


@asyncio.coroutine
@hook.regex("([^ ]*) is soaking [0-9]* shibes with ([0-9\.]*) Doge each. Total: [0-9\.]*")
def soaked_first(match, event):
    """
    :type match: re.__Match[str]
    :type event: obrbot.event.Event
    """
    if event.nick != doge_nick:
        return

    second = yield from event.wait_for_message("(.*)", nick=event.nick, chan=event.chan_name)
    if event.conn.bot_nick not in second.group(1).lower().split():
        if random.random() > 0.0625:
            # Random 1 in 16 chance to thank someone who didn't soak us
            # They deserve gratitude as well.
            # But we don't want to be annoying and thank *everyone* who didn't soak us.
            event.message("ty")
        return  # This checks if we were being soaked.

    doge_amount_added = int(match.group(2))
    yield from add_doge(event, doge_amount_added)


@asyncio.coroutine
@hook.regex("\[Wow\!\] ([^ ]*) sent ([^ ]*) ([0-9*]\.?[0-9]*) Doge")
def tipped(match, event):
    sender = match.group(1)
    if match.group(2).lower() != event.conn.nick.lower():
        return  # if we weren't tipped
    amount = float(match.group(3))
    current = yield from get_raw_balance(event)
    current += amount
    if current > max_doge:
        event.message("Thank you {}, you've tipped the balance! {} will be soaked soon.".format(sender, max_doge))
    else:
        event.message("Thanks for the tip, {}! {} more doge to go!".format(sender, max_doge - current))
    yield from add_doge(event, amount)


@asyncio.coroutine
@hook.command("balance", autohelp=False)
def doge_balance(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from get_raw_balance(event)
    return "Balance: {}".format(balance)
