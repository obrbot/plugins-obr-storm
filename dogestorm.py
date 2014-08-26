import asyncio
import datetime
from decimal import Decimal
import logging
import random

from obrbot import hook

plugin_info = {
    "plugin_category": "channel-specific",
    "command_category_name": "DogeStorm"
}

doge_nick = 'DogeWallet'
doge_channel = '#doge-coin'
doge_required_for_storm = 400

# Don't thank the same person more than every this number of seconds
thank_every_seconds = 30

# Time between storms
time_between_storms = datetime.timedelta(hours=38)
storm_length = datetime.timedelta(minutes=10)

logger = logging.getLogger('obrbot')

balance_key = 'obrbot:plugins:doge-storm:balance'
soaked_key = 'obrbot:plugins:doge-storm:soaked'
next_storm_key = 'obrbot:plugins:doge-storm:next-storm-time'
storm_running_key = 'obrbot:plugins:doge-storm:is-storm-running'
thanked_timer_key = 'obrbot:plugins:doge-storm:thanked:{}'


@asyncio.coroutine
def raw_get_balance(event):
    """
    :type event: obrbot.event.Event
    """
    raw_result = yield from event.async(event.db.get, balance_key)
    if raw_result is None:
        return 0
    else:
        return Decimal(raw_result.decode())


@asyncio.coroutine
def raw_add_balance(event, balance):
    """
    :type event: obrbot.event.Event
    """
    logger.info("Adding {} to balance".format(balance))
    raw_result = yield from event.async(event.db.incrbyfloat, balance_key, balance)
    return Decimal(raw_result)


@asyncio.coroutine
def raw_set_balance(event, balance):
    """
    :type event: obrbot.event.Event
    """
    raw_result = yield from event.async(event.db.set, balance_key, balance)
    return raw_result


@asyncio.coroutine
def raw_next_storm(event):
    """
    :type event: obrbot.event.Event
    """
    raw_result = yield from event.async(event.db.get, next_storm_key)
    if raw_result is None:
        return None
    else:
        return datetime.datetime.utcfromtimestamp(int(raw_result))


@asyncio.coroutine
def set_next_storm(event, time):
    """
    :type event: obrbot.event.Event
    :type time: datetime.datetime
    """
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = time - epoch
    timestamp = delta.total_seconds() * 1000
    raw_result = yield from event.async(event.db.set, next_storm_key, timestamp)
    return raw_result


@asyncio.coroutine
def raw_get_soaked(event):
    """
    :type event: obrbot.event.Event
    """
    raw_result = yield from event.async(event.db.get, soaked_key)
    return Decimal(raw_result.decode())


@asyncio.coroutine
def raw_add_soaked(event, balance):
    """
    :type event: obrbot.event.Event
    """
    raw_result = yield from event.async(event.db.incrbyfloat, soaked_key, balance)
    return Decimal(raw_result)


@asyncio.coroutine
def already_thanked(event, nick):
    """
    :type event: obrbot.event.Event
    """
    key = thanked_timer_key.format(nick.lower())
    result = yield from event.async(event.db.get, key)
    if result is not None:
        logger.info("Already thanked {}, not thanking again".format(nick))
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


@asyncio.coroutine
def update_balance(event):
    """
    :type event: obrbot.event.Event
    """
    stored_balance = yield from raw_get_balance(event)

    event.message("balance", target=doge_nick)
    balance = Decimal((yield from event.conn.wait_for("^([0-9]*\.?[0-9]*)$", nick=doge_nick, chan=doge_nick)).group(1))

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
    if balance > doge_required_soak:
        active = yield from get_active(event)
        if active < 3:
            event.message("Would have soaked {}, but there are less than 3 active users.".format(balance))
            event.message("When more users are active, tip 1 doge and the soak will be re-initiated")
            return
        event.message("[Soak] Soaking {}!".format(balance))

        balance = yield from update_balance(event)
        balance -= reserves  # Since we had to update_balance again, re-apply reserves

        event.message(".soak {}".format(int(balance / active)))

        soaked_future = event.conn.wait_for(
            "{} is soaking [0-9]* shibes with [0-9\.]* Doge each. Total: ([0-9\.]*)"
            .format(event.conn.bot_nick), nick=doge_nick)

        failed_future = event.conn.wait_for("Not enough doge.", nick=doge_nick, chan=doge_nick)

        done, pending = yield from asyncio.wait([soaked_future, failed_future], loop=event.loop,
                                                return_when=asyncio.FIRST_COMPLETED, timeout=20)

        if soaked_future in done:
            match = yield from soaked_future
            soaked_amount = Decimal(match.group(1))
            new_balance = yield from raw_add_balance(event, -soaked_amount)
            yield from raw_add_soaked(event, soaked_amount)
            # Sleep before announcing next soak
            yield from asyncio.sleep(1 + random.random(), loop=event.loop)
            event.message("[Soak] Saving up for {}Ð soak! {} more doge required!".format(
                doge_required_soak, get_amount_till_next_soak(new_balance)))
        elif failed_future in done:
            event.message("[Soak] Soak failed! Not enough doge, even after double-checking!", "Ping Dabo!")
        else:
            event.message("[Soak] Soak failed! DogeWallet failed to respond!", "Ping Dabo!")
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
        if doge_amount_given >= 3 and random.random() < 0.6:
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(5 + random.random() * 10, loop=event.loop)
                event.message("ty")
        # We were soaked
        asyncio.async(add_doge(event, doge_amount_given), loop=event.loop)
    else:
        if random.random() < 0.25:
            # Random 1 in 16 chance to thank someone who didn't soak us
            # They deserve gratitude as well.
            # But we don't want to be annoying and thank *everyone* who didn't soak us.
            if not (yield from already_thanked(event, giving_nick)):
                yield from asyncio.sleep(5 + random.random() * 10, loop=event.loop)
                event.message("ty")
        return  # This checks if we were being soaked.


@asyncio.coroutine
@hook.regex("\[Wow\!\] ([^ ]*) sent ([^ ]*) ([0-9*]\.?[0-9]*) Doge")
def tipped(match, event):
    sender = match.group(1)
    if match.group(2).lower() != event.conn.bot_nick.lower():
        return  # if we weren't tipped
    amount = Decimal(match.group(3))
    current = yield from raw_get_balance(event)
    current -= yield from raw_get_reserves(event)
    current += amount * (100 - reserver_each_storm) / 100  # don't count new reserves
    if current > doge_required_soak:
        event.message("[Soak] Thank you {}, you've tipped the balance! Soak incoming!"
                      .format(sender, current))
    else:
        event.message("Thanks for the tip, {}! {} more doge till a {}Ð soak!".format(
            sender, get_amount_till_next_soak(current), doge_required_soak))

    yield from add_doge(event, amount)


@asyncio.coroutine
@hook.command("balance", autohelp=False)
def balance_command(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_balance(event)
    reserves = yield from raw_get_reserves(event)
    return "Balance: {}".format(balance - reserves)


@asyncio.coroutine
@hook.command("update-balance", autohelp=False)
def update_balance_command(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from update_balance(event)
    reserves = yield from raw_get_reserves(event)
    return "Balance: {}".format(balance - reserves)


@asyncio.coroutine
@hook.command("reserves", autohelp=False)
def reserves_command(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_reserves(event)
    return "Reserves: {}".format(balance)


@asyncio.coroutine
@hook.command("soaked", autohelp=False)
def soaked_command(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_soaked(event)
    return "Total Soaked: {}".format(balance)


@asyncio.coroutine
@hook.command("raw-balance", autohelp=False)
def raw_reserves_command(event):
    """
    :type event: obrbot.event.Event
    """
    balance = yield from raw_get_balance(event)
    reserves = yield from raw_get_reserves(event)
    return "Total: {}, Reserves: {}, Balance: {}".format(balance, reserves, balance - reserves)
