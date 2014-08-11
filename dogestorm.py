import asyncio
import logging
import random

from obrbot import hook

doge_nick = 'DogeWallet'
doge_channel = '#doge-coin'
doge_required_soak = 10

# This percentage of all donated DogeCoin will be 'reserved' and not used in 1000-coin soaks.
# This is saving up for future DogeCoin 'soak storms' which aren't currently implemented.
reserve_percentage = 10

# Don't thank the same person more than every this number of seconds
thank_every_seconds = 30

logger = logging.getLogger('obrbot')

balance_key = 'obrbot:plugins:doge-storm:balance'
reserves_key = 'obrbot:plugins:doge-storm:reserved'
thanked_timer_key = 'obrbot:plugins:doge-storm:thanked:{}'


@asyncio.coroutine
def raw_get_reserves(event):
    """
    :type event: obrbot.event.Event
    """
    result = yield from event.async(event.db.get, reserves_key)
    if result is None:
        return 0
    else:
        return float(result)


@asyncio.coroutine
def raw_add_reserves(event, balance):
    logger.info("Adding {} to reserves".format(balance))
    raw_result = yield from event.async(event.db.incrbyfloat, reserves_key, balance)
    return float(raw_result)


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
    logger.info("Adding {} to balance".format(balance))
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
    active = (yield from event.conn.wait_for("^Active Shibes: ([0-9]*)$", nick=doge_nick, chan=doge_nick)).group(1)

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
    balance = float((yield from event.conn.wait_for("^([0-9]*\.?[0-9]*)$", nick=doge_nick, chan=doge_nick)).group(1))

    if stored_balance != balance:
        logger.info("Updated balance from {} to {}".format(stored_balance, balance))
        yield from raw_set_balance(event, balance)

    return balance


@asyncio.coroutine
def add_doge(event, amount_added):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_add_balance(event, amount_added)
    # We don't want to count reserves for our smaller soaks
    reserves = yield from raw_add_reserves(event, amount_added * reserve_percentage / 100)
    balance -= yield from raw_add_reserves(event, amount_added * reserve_percentage / 100)
    if balance > doge_required_soak:
        active = yield from get_active(event)
        if active < 3:
            event.message("Would have soaked {}, but there are less than 3 active users.")
            event.message("When more users are active, tip 1 doge and the soak will be re-initiated")
            return
        event.message("Soaking {}!".format(balance))

        balance = yield from update_balance(event)
        balance -= reserves  # Since we had to update_balance again, re-apply reserves

        event.message(".soak {}".format(int(balance / active)))

        soaked_future = event.conn.wait_for(
            "{} is soaking [0-9]* shibes with ([0-9\.]*) Doge each. Total: [0-9\.]*"
            .format(event.conn.bot_nick), nick=doge_nick)

        failed_future = event.conn.wait_for("Not enough doge.", nick=doge_nick, chan=doge_nick)

        done, pending = yield from asyncio.wait([soaked_future, failed_future], loop=event.loop,
                                                return_when=asyncio.FIRST_COMPLETED, timeout=20)

        if soaked_future in done:
            match = yield from soaked_future
            yield from raw_add_balance(event, -float(match.group(1)))
        for future in pending:
            future.cancel()  # we don't care anymore


@asyncio.coroutine
@hook.regex("([^ ]*) is soaking [0-9]* shibes with ([0-9\.]*) Doge each. Total: [0-9\.]*", single_thread=True)
def soaked_regex(match, event):
    """
    :type match: re.__Match[str]
    :type event: obrbot.event.Event
    """
    giving_nick = match.group(1)

    if event.nick != doge_nick:
        return

    if giving_nick.lower() == event.conn.bot_nick.lower():
        return

    second = yield from event.conn.wait_for("(.*)", nick=event.nick, chan=event.chan_name)

    doge_amount_given = int(match.group(2))

    if event.conn.bot_nick.lower() in second.group(1).lower().split():
        # If the user gave us more than 5 or more doge, thank them half of the time.
        if doge_amount_given >= 5 and random.random() > 0.5:
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(0.25 + random.random(), loop=event.loop)
                event.message("ty")
        # We were soaked
        asyncio.async(add_doge(event, doge_amount_given), loop=event.loop)
    else:
        if random.random() > 0.0625:
            # Random 1 in 16 chance to thank someone who didn't soak us
            # They deserve gratitude as well.
            # But we don't want to be annoying and thank *everyone* who didn't soak us.
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(0.25 + random.random(), loop=event.loop)
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
    current -= yield from raw_get_reserves(event)
    current += amount * (100 - reserve_percentage) / 100  # don't count new reserves
    if current > doge_required_soak:
        event.message("Thank you {}, you've tipped the balance! {} will be soaked after communications with DogeWallet."
                      .format(sender, current))
    else:
        event.message("Thanks for the tip, {}! {} more doge to go!".format(sender, doge_required_soak - current))
    yield from add_doge(event, amount)


@asyncio.coroutine
@hook.command("balance", autohelp=False)
def doge_balance(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_balance(event)
    reserves = yield from raw_add_reserves(event)
    return "Balance: {}".format(balance - reserves)


@asyncio.coroutine
@hook.command("reserves", autohelp=False, permissions=["bot.manage"])
def doge_reserves(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_reserves(event)
    return "Reserves: {}".format(balance)
