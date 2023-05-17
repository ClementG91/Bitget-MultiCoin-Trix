import json
import time
from datetime import datetime
import discord
import ta
from spot_bitget import SpotBitget

# Displaying the start time of execution
now = datetime.now()
current_time = now.strftime("%d/%m/%Y %H:%M:%S")
print("--- Start Execution Time:", current_time, "---")

# Reading authentication information from a JSON file
f = open(
    "./secret.json",
)
secret = json.load(f)
f.close()

# Selecting the account and configuring the API connection
account_to_select = "bitget_exemple"
production = False

bitget = SpotBitget(
    apiKey=secret[account_to_select]["apiKey"],
    secret=secret[account_to_select]["secret"],
    password=secret[account_to_select]["password"],
)

# List of trading pairs to monitor
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
    "AVAX/USDT:USDT"
]

subAccountName = 'EBot'
MESSAGE_TEMPLATE = {
    "message_sell": "{}: Sell {} at {}",
    "message_keep": "{}: Keep {}",
    "message_buy": "{}: Buy {} {} at {} USDT",
    "message_wallet": "{}: {} USDT",
    "message_erreur": "{}: Unable to retrieve the last {} candles of {}.",
    "message_attente": "{}: No ongoing or potential trades."
}
message_list = []

# Timeframe to use for technical analysis
timeframe = "1h"
# Displaying the used parameters
print(f"--- {pairlist} {timeframe} ---")

# Loading historical data for each trading pair in the list
dflist = {}
nbOfCandles = 210
ratio = [int((nbOfCandles*(100/(i+1)))/100) for i in range(0, 3)]
idex = 0

for pair in pairlist:
    # Attempting to retrieve historical data for the current pair
    request_success = False
    while request_success == False:
        try:
            df = bitget.get_more_last_historical_async(pair, timeframe, 1000)
            dflist[pair.replace('/USDT:USDT', '')] = df
            request_success = True
        except Exception as err:
            # If an error occurs while retrieving data, display an error message and retry
            print(f"Error, details: {err}")
            message_list.append(MESSAGE_TEMPLATE['message_erreur'].format(
                subAccountName, nbOfCandles, pair))

# -- Variables for indicators --
trixLength = 9
trixSignal = 21

# -- Parameters --
maxOpenPosition = 2
stochOverBought = 0.80
stochOverSold = 0.20
TpPct = 5

for coin in dflist:
    # -- Drop all columns we do not need --
    dflist[coin].drop(columns=dflist[coin].columns.difference(
        ['open', 'high', 'low', 'close', 'volume']), inplace=True)

    dflist[coin]['TRIX'] = ta.trend.ema_indicator(ta.trend.ema_indicator(ta.trend.ema_indicator(
        close=dflist[coin]['close'], window=trixLength), window=trixLength), window=trixLength)
    dflist[coin]['TRIX_PCT'] = dflist[coin]["TRIX"].pct_change() * 100
    dflist[coin]['TRIX_SIGNAL'] = ta.trend.sma_indicator(
        dflist[coin]['TRIX_PCT'], trixSignal)
    dflist[coin]['TRIX_HISTO'] = dflist[coin]['TRIX_PCT'] - \
        dflist[coin]['TRIX_SIGNAL']
    dflist[coin]['STOCH_RSI'] = ta.momentum.stochrsi(
        close=dflist[coin]['close'], window=14, smooth1=3, smooth2=3)
print("Data and Indicators loaded 100%")

# -- Condition to BUY --


def buyCondition(row, previousRow=None):
    if (
        row['TRIX_HISTO'] > 0
        and row['STOCH_RSI'] <= stochOverBought
    ):
        return True
    else:
        return False

# -- Condition to SELL --


def sellCondition(row, previousRow=None):
    if (
        row['TRIX_HISTO'] < 0
        and row['STOCH_RSI'] >= stochOverSold
    ):
        return True
    else:
        return False


usdBalance = bitget.get_balance_of_one_coin('USDT')
# Dictionary to store the USD balance per coin
balanceInUsdPerCoin_dict = {}
# Iterate over each coin in dflist
for coin in dflist:
    symbol = coin + '/USDT'
    # Get the current price of the coin
    lastPrice = float(bitget.convert_price_to_precision(
        symbol, bitget.get_bid_ask_price(symbol)['ask']))
    print(f"Coin:", coin)
    print(f"Last Price:", lastPrice)
    # Get the current balance of the coin
    coinBalance = bitget.get_balance_of_one_coin(coin)
    print(f"Coin Balance:", coinBalance)
    # Calculate the balance in USD per coin by multiplying the coin balance by the last price
    balanceInUsdPerCoin = coinBalance * lastPrice
    print(f"Balance In USD Per Coin:", balanceInUsdPerCoin)
    # Add the balance in USD per coin to the dictionary
    balanceInUsdPerCoin_dict[coin] = balanceInUsdPerCoin

print(f"Balance In USD Per Coin dict:", balanceInUsdPerCoin_dict)
# Calculate the total balance in USD by adding the USD balance of each coin and the base USD balance (usdBalance)
totalBalanceInUsd = sum(balanceInUsdPerCoin_dict.values()) + usdBalance
print(f"Total Balance In USD:", totalBalanceInUsd)
coinPositionlist = []
# Iterate over each coin in the balanceInUsdPerCoin_dict dictionary
for coin in balanceInUsdPerCoin_dict:
    # Check if the coin value is greater than 0.10 * totalBalanceInUsd
    if balanceInUsdPerCoin_dict[coin] > 0.10 * totalBalanceInUsd:
        # Add the coin to the coinPositionlist
        coinPositionlist.append(coin)
# Calculate the number of open positions by counting the number of elements in coinPositionlist
openPositions = len(coinPositionlist)
print(f"Open Positions:", openPositions)

# Sales
for coin in coinPositionlist:
    # Check if the sell condition is met
    if sellCondition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]) == True:
        # Decrement the number of open positions
        openPositions -= 1
        # Set the trading pair symbol
        symbol = coin + '/USDT'
        time.sleep(1)
        # Get the sell price as a floating-point precision
        sellPrice = float(bitget.convert_price_to_precision(
            symbol, bitget.get_bid_ask_price(symbol)['ask']))
        coinBalance = bitget.get_balance_of_one_coin(coin)
        # Perform a market sell for the amount of cryptocurrency held
        sell = bitget.place_market_order(symbol, 'sell', coinBalance)
        # Display a message indicating that the sale has been executed
        print(f"Sell")
        # Add a message to the message list with the sale details
        message_list.append(MESSAGE_TEMPLATE['message_sell'].format(
            subAccountName, str(coin), str(sellPrice)))
    else:
        # If the sell condition is not met, display a message to wait
        print(f"Wait")
        # Add a message to the message list indicating to keep the position
        message_list.append(MESSAGE_TEMPLATE['message_keep'].format(
            subAccountName, str(coin)))
# Buying
if openPositions < maxOpenPosition:
    # Check each cryptocurrency in dflist
    for coin in dflist:
        # Check if the cryptocurrency is not already in the coinPositionlist
        if coin not in coinPositionlist:
            # Check if the buy condition is met and if the number of open positions is less than the maximum allowed
            if buyCondition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]) == True and openPositions < maxOpenPosition:
                time.sleep(1)
                # Set the trading pair symbol
                symbol = coin + '/USDT'
                # Get the buy price as a floating-point precision
                buyPrice = float(bitget.convert_price_to_precision(
                    symbol, bitget.get_bid_ask_price(symbol)['ask']))
                # Calculate the take profit price by adding a percentage to the buy price
                tpPrice = float(bitget.convert_price_to_precision(
                    symbol, buyPrice + TpPct * buyPrice))
                # Calculate the buy quantity in USD based on the USD balance and the maximum number of open positions
                buyQuantityInUsd = bitget.get_balance_of_one_coin('USDT') * 1 / \
                    (maxOpenPosition - openPositions)

                # Reduce the buy quantity by 5% if it's the last position to open
                if openPositions == maxOpenPosition - 1:
                    buyQuantityInUsd = 0.95 * buyQuantityInUsd

                # Convert the buy quantity to the required precision for the trading pair
                buyAmount = float(bitget.convert_amount_to_precision(symbol, float(
                    bitget.convert_amount_to_precision(
                        symbol, buyQuantityInUsd / buyPrice)
                )))
                # Display the values of certain parameters for debugging
                print("usdBalance:", usdBalance, "buyQuantityInUsd:", buyQuantityInUsd,
                      "buyAmount:", buyAmount, "buyPrice:", buyPrice, "openPositions:", openPositions)
                time.sleep(2)
                # Place a limit buy order for the specified quantity and price, with reduce disabled
                buy = bitget.place_limit_order(
                    symbol, 'buy', buyAmount, buyPrice, reduce=False)
                # Add a message to the message list with the details of the purchase
                message_list.append(MESSAGE_TEMPLATE['message_buy'].format(
                    subAccountName, str(buyAmount), str(coin), str(buyPrice)))
                # Display a message indicating that the purchase has been made
                print(f"Buy")
                # Increment the number of open positions
                openPositions += 1

message_list.append(MESSAGE_TEMPLATE['message_wallet'].format(
    subAccountName, str(usdBalance)))

# Create an Intents object with the default intents
intents = discord.Intents.default()
# Optional: disable the typing intent
intents.typing = False
# Optional: disable the presence intent
intents.presences = False
TOKEN = secret["discord_exemple"]["token"]
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    # Join the message list with "\n" separator
    msg = "\n".join(message_list)
    id = int(secret["discord_exemple"]["channel"])
    channel = client.get_channel(id)
    await channel.send(msg)
    await client.close()

client.run(TOKEN)
