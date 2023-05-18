import json
import time
from datetime import datetime
import discord
import ta
from spot_bitget import SpotBitget

MESSAGE_TEMPLATE = {
    "message_sell": "{}: Sell {} at {}",
    "message_keep": "{}: Keep {}",
    "message_buy": "{}: Buy {} {} at {} USDT",
    "message_wallet": "{}: {} USDT",
    "message_erreur": "{}: Unable to retrieve the last {} candles of {}.",
    "message_attente": "{}: No ongoing or potential trades."
}

subAccountName = 'EBot'

# Timeframe to use for technical analysis
timeframe = "1h"

# -- Variables for indicators --
trixLength = 9
trixSignal = 21

# -- Parameters --
maxOpenPosition = 2
stochOverBought = 0.80
stochOverSold = 0.20
TpPct = 5


def get_time_now():
    now = datetime.now()
    current_time = now.strftime("%d/%m/%Y %H:%M:%S")
    return current_time


def load_secret(file_path):
    with open(file_path) as f:
        secret = json.load(f)
    return secret


def configure_bitget(account_to_select, secret, production=False):
    bitget = SpotBitget(
        apiKey=secret[account_to_select]["apiKey"],
        secret=secret[account_to_select]["secret"],
        password=secret[account_to_select]["password"],
    )
    return bitget


def load_historical_data(bitget, pairlist, timeframe, nbOfCandles, message_list=None):

    dflist = {}
    ratio = [int((nbOfCandles * (100 / (i + 1))) / 100) for i in range(0, 3)]

    for pair in pairlist:
        try:
            df = bitget.get_more_last_historical_async(pair, timeframe, 1000)
            dflist[pair.replace('/USDT:USDT', '')] = df
        except Exception as err:
            print(f"Error, details: {err}")
            if message_list is not None:
                message_list.append(MESSAGE_TEMPLATE['message_erreur'].format(
                    subAccountName, nbOfCandles, pair))

    return dflist


def calculate_indicators(dflist):
    for coin in dflist:
        df = dflist[coin]
        df.drop(columns=df.columns.difference(
            ['open', 'high', 'low', 'close', 'volume']), inplace=True)
        df['TRIX'] = ta.trend.ema_indicator(
            ta.trend.ema_indicator(ta.trend.ema_indicator(
                close=df['close'], window=trixLength), window=trixLength),
            window=trixLength
        )
        df['TRIX_PCT'] = df["TRIX"].pct_change() * 100
        df['TRIX_SIGNAL'] = ta.trend.sma_indicator(
            df['TRIX_PCT'], window=trixSignal)
        df['TRIX_HISTO'] = df['TRIX_PCT'] - df['TRIX_SIGNAL']
        df['STOCH_RSI'] = ta.momentum.stochrsi(
            close=df['close'], window=14, smooth1=3, smooth2=3)
        df['RSI'] = ta.momentum.rsi(close=df['close'], window=14)
        df.dropna(inplace=True)

    return dflist


def calculate_balances(bitget, dflist):
    usd_balance = bitget.get_balance_of_one_coin('USDT')
    balance_in_usd_per_coin = {}

    for coin in dflist:
        symbol = coin + '/USDT'
        last_price = float(bitget.convert_price_to_precision(
            symbol, bitget.get_bid_ask_price(symbol)['ask']))
        coin_balance = bitget.get_balance_of_one_coin(coin)
        balance_in_usd_per_coin[coin] = coin_balance * last_price

    return usd_balance, balance_in_usd_per_coin


def calculate_positions(balance_in_usd_per_coin, total_balance_in_usd):
    coin_position_list = []

    for coin in balance_in_usd_per_coin:
        if balance_in_usd_per_coin[coin] > 0.10 * total_balance_in_usd:
            coin_position_list.append(coin)

    return coin_position_list


def execute_sales(bitget, coin_position_list, dflist, message_list, open_positions):
    for coin in coin_position_list:
        if sell_condition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]):
            open_positions -= 1
            symbol = coin + '/USDT'
            sell_price = float(bitget.convert_price_to_precision(
                symbol, bitget.get_bid_ask_price(symbol)['ask']))
            coin_balance = bitget.get_balance_of_one_coin(coin)
            sell = bitget.place_market_order(symbol, 'sell', coin_balance)
            message_list.append(MESSAGE_TEMPLATE['message_sell'].format(
                subAccountName, str(coin), str(sell_price)))
        else:
            message_list.append(MESSAGE_TEMPLATE['message_keep'].format(
                subAccountName, str(coin)))

    return message_list, open_positions


def buy_condition(row, previousRow=None):
    return row['TRIX_HISTO'] > 0 and row['STOCH_RSI'] <= stochOverBought


def sell_condition(row, previousRow=None):
    return row['TRIX_HISTO'] < 0 and row['STOCH_RSI'] >= stochOverSold


def execute_buys(bitget, dflist, message_list, open_positions, coin_position_list, usd_balance):
    if open_positions < maxOpenPosition:
        for coin in dflist:
            if coin not in coin_position_list:
                if buy_condition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]) and open_positions < maxOpenPosition:
                    symbol = coin
                    buy_price = float(bitget.convert_price_to_precision(
                        symbol, bitget.get_bid_ask_price(symbol)['ask']))
                    tp_price = float(bitget.convert_price_to_precision(
                        symbol, buy_price + TpPct * buy_price))
                    buy_quantity_in_usd = bitget.get_balance_of_one_coin(
                        'USDT') * 1 / (maxOpenPosition - open_positions)

                    if open_positions == maxOpenPosition - 1:
                        buy_quantity_in_usd = 0.95 * buy_quantity_in_usd

                    buy_amount = float(bitget.convert_amount_to_precision(
                        symbol, float(bitget.convert_amount_to_precision(
                            symbol, buy_quantity_in_usd / buy_price))
                    ))

                    buy = bitget.place_limit_order(
                        symbol, 'buy', buy_amount, buy_price, reduce=False)
                    message_list.append(
                        MESSAGE_TEMPLATE['message_buy'].format(
                            subAccountName, str(buy_amount), str(coin), str(buy_price))
                    )
                    open_positions += 1

    return message_list, open_positions


def send_messages_to_discord(client, secret, message_list):
    TOKEN = secret["discord_exemple"]["token"]

    @client.event
    async def on_ready():
        channel_id = int(secret["discord_exemple"]["channel"])
        channel = client.get_channel(channel_id)

        for message in message_list:
            print(message)
            await channel.send(message)

        await client.close()

    client.run(TOKEN)


def main():
    print(get_time_now())
    # Initialize bitget API client
    secret = load_secret("secret.json")
    bitget = configure_bitget("bitget_exemple", secret, production=True)

    # Initialize Discord client
    intents = discord.Intents.default()
    intents.typing = False
    intents.presences = False
    client = discord.Client(intents=intents)

    # Define your list of coins
    pairlist = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "BNB/USDT:USDT",
        "XRP/USDT:USDT",
        "SOL/USDT:USDT",
        "SHIB/USDT:USDT",
        "CHZ/USDT:USDT",
        "DOGE/USDT:USDT",
        "MATIC/USDT:USDT",
        "AVAX/USDT:USDT",
    ]

    # Load historical data
    message_list = []
    dflist = load_historical_data(
        bitget, pairlist, timeframe, 1000, message_list)

    # Calculate indicators
    dflist = calculate_indicators(dflist)

    # Calculate balances
    usd_balance, balance_in_usd_per_coin = calculate_balances(bitget, dflist)

    # Calculate positions
    coin_position_list = calculate_positions(
        balance_in_usd_per_coin, usd_balance)

    # Execute sales if sell condition is met
    open_positions = len(coin_position_list)
    message_list, open_positions = execute_sales(
        bitget, coin_position_list, dflist, message_list, open_positions
    )

    # Execute buys if buy condition is met
    message_list, open_positions = execute_buys(
        bitget, dflist, message_list, open_positions, coin_position_list, usd_balance
    )

    # Send messages to Discord
    send_messages_to_discord(client, secret, message_list)
    print(get_time_now())


if __name__ == "__main__":
    main()
