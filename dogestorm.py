import asyncio
import logging
import random

from obrbot import hook

doge_nick = 'DogeWallet'
doge_required = 1000

# Don't thank the same person more than every this number of seconds
thank_every_seconds = 20

logger = logging.getLogger('obrbot')

balance_key = 'obrbot:plugins:doge-storm:balance'
thanked_timer_key = 'obrbot:plugins:doge-storm:thanked:{}'


@asyncio.coroutine
def raw_get_balance(event):
    """
    :type event: obrbot.event.Event
    """
    result = yield from event.async(event.db.get, balance_key)
    if result is None:
        return 0
    else:
        return float(result)


@asyncio.coroutine
def raw_add_balance(event, balance):
    raw_result = yield from event.async(event.db.incrbyfloat, balance_key, balance)
    return float(raw_result)


@asyncio.coroutine
def raw_set_balance(event, balance):
    raw_result = yield from event.async(event.db.set, balance_key, balance)
    return float(raw_result)


@asyncio.coroutine
def already_thanked(event, nick):
    """
    :type event: obrbot.event.Event
    """
    key = thanked_timer_key.format(nick.lower())
    result = yield from event.async(event.db.get, key)
    if result is not None:
        logger.warning("Already thanked {}, not thanking again".format(nick))
        return True
    yield from event.async(event.db.setex, key, thank_every_seconds, '')
    return False


@asyncio.coroutine
def get_active(event):
    """
    :type event: obrbot.event.Event
    """
    event.message("active", target=doge_nick)
    active = (yield from event.wait_for_message("^Active Shibes: ([0-9]*)$", nick=doge_nick, chan=doge_nick)).group(1)

    print("Active: " + active)
    return int(active)


# this can be used as a command, or just as a function
@asyncio.coroutine
@hook.command("update-balance", autohelp=False)
def update_balance(event):
    """
    :type event: obrbot.event.Event
    """
    stored_balance = yield from raw_get_balance(event)

    event.message("balance", target=doge_nick)
    balance = float((yield from event.wait_for_message("^([0-9]*\.?[0-9]*)$", nick=doge_nick, chan=doge_nick)).group(1))

    if stored_balance != balance:
        yield from raw_set_balance(event, balance)

    return balance


@asyncio.coroutine
def add_doge(event, amount_added):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_add_balance(event, amount_added)
    if balance > doge_required:
        active = yield from get_active(event)
        if active < 1:
            return

        balance = yield from update_balance(event)

        event.message(".soak {}".format(balance / active))
        yield from update_balance(event)


@asyncio.coroutine
@hook.regex("([^ ]*) is soaking [0-9]* shibes with ([0-9\.]*) Doge each. Total: [0-9\.]*")
def soaked_regex(match, event):
    """
    :type match: re.__Match[str]
    :type event: obrbot.event.Event
    """
    giving_nick = match.group(1)

    if event.nick != doge_nick:
        return

    second = yield from event.wait_for_message("(.*)", nick=event.nick, chan=event.chan_name)

    doge_amount_given = int(match.group(2))

    if event.conn.bot_nick.lower() in second.group(1).lower().split():
        # We were soaked
        asyncio.async(add_doge(event, doge_amount_given), loop=event.loop)
        # If the user gave us more than 5 or more doge, thank them half of the time.
        if doge_amount_given >= 5 and random.random() > 0.5:
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(0.5, loop=event.loop)
                event.message("ty")
    else:
        if random.random() > 0.125:
            # Random 1 in 8 chance to thank someone who didn't soak us
            # They deserve gratitude as well.
            # But we don't want to be annoying and thank *everyone* who didn't soak us.
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(0.5, loop=event.loop)
                event.message("ty")
        return  # This checks if we were being soaked.


@asyncio.coroutine
@hook.regex("\[Wow\!\] ([^ ]*) sent ([^ ]*) ([0-9*]\.?[0-9]*) Doge")
def tipped(match, event):
    sender = match.group(1)
    if match.group(2).lower() != event.conn.bot_nick.lower():
        return  # if we weren't tipped
    amount = float(match.group(3))
    current = yield from raw_get_balance(event)
    current += amount
    if current > doge_required:
        event.message("Thank you {}, you've tipped the balance! {} will be soaked after communications with DogeWallet."
                      .format(sender, doge_required))
    else:
        event.message("Thanks for the tip, {}! {} more doge to go!".format(sender, doge_required - current))
    yield from add_doge(event, amount)


@asyncio.coroutine
@hook.command("balance", autohelp=False)
def doge_balance(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_balance(event)
    return "Balance: {}".format(balance)
