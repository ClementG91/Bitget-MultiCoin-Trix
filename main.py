# Importation des modules
import json
import time
from datetime import datetime
import discord
import ta
from spot_bitget import SpotBitget
# Affichage de l'heure de début d'exécution
now = datetime.now()
current_time = now.strftime("%d/%m/%Y %H:%M:%S")
print("--- Start Execution Time :", current_time, "---")

# Lecture des informations d'authentification à partir d'un fichier JSON
f = open(
    "./secret.json",
)
secret = json.load(f)
f.close()

# Sélection du compte et paramétrage de la connexion API
account_to_select = "bitget_exemple"
production = False

bitget = SpotBitget(
    apiKey=secret[account_to_select]["apiKey"],
    secret=secret[account_to_select]["secret"],
    password=secret[account_to_select]["password"],
)

# Liste des paires de trading à surveiller
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
    "message_sell": "{} : Vente {} à {} ",
    "message_keep": "{} : Conserver {} ",
    "message_buy": "{} : Achat de {} {} à {} USDT ",
    "message_wallet": "{} : {} USDT ",
    "message_erreur": "{} : Impossible de récupérer les {} dernières bougies de {}.",
    "message_attente": "{} : Aucun Trade en cours ou à prendre."
}
message_list = []

# Période de temps à utiliser pour l'analyse technique
timeframe = "1h"
# Affichage des paramètres utilisés
print(f"--- {pairlist} {timeframe} ---")

# Chargement des données historiques pour chaque paire de trading dans la liste
dflist = {}
nbOfCandles = 210
ratio = [int((nbOfCandles*(100/(i+1)))/100)for i in range(0, 3)]
idex = 0

for pair in pairlist:
    # Tentative de récupération des données historiques pour la paire courante
    request_success = False
    while (request_success == False):
        try:
            df = bitget.get_more_last_historical_async(pair, timeframe, 1000)
            dflist[pair.replace('/USDT:USDT', '')] = df
            request_success = True
        except Exception as err:
            # En cas d'erreur lors de la tentative de récupération des données, afficher un message d'erreur et réessayer
            print(f"Erreur, détails : {err}")
            message_list.append(MESSAGE_TEMPLATE['message_erreur'].format(
                subAccountName, nbOfCandles, pair))

# -- Variables pour les indicateurs --
trixLength = 9
trixSignal = 21

# -- Parametre --
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
    dflist[coin]['TRIX_PCT'] = dflist[coin]["TRIX"].pct_change()*100
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
# Dictionnaire pour stocker le solde en USD par coin
balanceInUsdPerCoin_dict = {}
# Parcourir chaque coin dans dflist
for coin in dflist:
    symbol = coin + '/USDT'
    # Obtenir le prix actuelle du coin
    lastPrice = float(bitget.convert_price_to_precision(
        symbol, bitget.get_bid_ask_price(symbol)['ask']))
    print(f"Coin:", coin)
    print(f"Last Price:", lastPrice)
    # Obtenir le solde actuelle du coin
    coinBalance = bitget.get_balance_of_one_coin(coin)
    print(f"Coin Balance:", coinBalance)
    # Calculer le solde en USD par coin en multipliant le solde de la coin par le dernier prix
    balanceInUsdPerCoin = coinBalance*lastPrice
    print(f"Balance In Usd Per Coin:", balanceInUsdPerCoin)
    # Ajouter le solde en USD par coin au dictionnaire
    balanceInUsdPerCoin_dict[coin] = balanceInUsdPerCoin

print(f"Balance In Usd Per Coin dict:", balanceInUsdPerCoin_dict)
# Calculer le solde total en USD en ajoutant le solde en USD de chaque coin et le solde en USD de base (usdBalance)
totalBalanceInUsd = sum(balanceInUsdPerCoin_dict.values()) + usdBalance
print(f"Total Balance In Usd:", totalBalanceInUsd)
coinPositionlist = []
# Parcourir chaque coin dans le dictionnaire balanceInUsdPerCoin_dict
for coin in balanceInUsdPerCoin_dict:
    # Vérifiez si la valeur du coin est supérieure à 0.05 * totalBalanceInUsd
    if balanceInUsdPerCoin_dict[coin] > 0.05 * totalBalanceInUsd:
        # Ajoutez le coin à la liste coinPositionlist
        coinPositionlist.append(coin)
# Calculer le nombre de positions ouvertes en comptant le nombre d'éléments dans coinPositionlist
openPositions = len(coinPositionlist)
print(f"Open Positions:", openPositions)

# Ventes
for coin in coinPositionlist:
    # Vérifier si la condition de vente est remplie
    if sellCondition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]) == True:
        # Décrémenter le nombre de positions ouvertes
        openPositions -= 1
        # Définir le symbole de la paire de trading
        symbol = coin+'/USDT'
        # Annuler les ordres en attente pour la paire de trading
        cancel = bitget.cancel_order_by_id(symbol)
        time.sleep(1)
        # Obtenir le prix de vente en tant que précision flottante
        sellPrice = float(bitget.convert_price_to_precision(
            symbol, bitget.get_bid_ask_price(symbol)['ask']))
        # Effectuer une vente de marché pour la quantité de crypto-monnaie possédée
        sell = bitget.place_market_order(symbol, 'sell', coinBalance[coin])
        # Afficher un message indiquant que la vente a été effectuée
        print(f"Vente")
        # Ajouter un message à la liste des messages avec les détails de la vente
        message_list.append(MESSAGE_TEMPLATE['message_sell'].format(
            subAccountName, str(coin), str(sellPrice)))
    else:
        # Si la condition de vente n'est pas remplie, afficher un message pour patienter
        print(f"Patienter")
        # Ajouter un message à la liste des messages indiquant de conserver la position
        message_list.append(MESSAGE_TEMPLATE['message_keep'].format(
            subAccountName, str(coin)))
# Achat
if openPositions < maxOpenPosition:
    # Vérifier chaque crypto-monnaie dans dflist
    for coin in dflist:
        # Vérifier si la crypto-monnaie n'est pas déjà présente dans la liste des positions de monnaies
        if coin not in coinPositionlist:
            # Vérifier si la condition d'achat est remplie et si le nombre de positions ouvertes est inférieur au maximum autorisé
            if buyCondition(dflist[coin].iloc[-2], dflist[coin].iloc[-3]) == True and openPositions < maxOpenPosition:
                time.sleep(1)
                # Définir le symbole de la paire de trading
                symbol = coin+'/USDT'
                # Obtenir le prix d'achat en tant que précision flottante
                buyPrice = float(bitget.convert_price_to_precision(
                    symbol, bitget.get_bid_ask_price(symbol)['ask']))
                # Calculer le prix de prise de profit en ajoutant un pourcentage au prix d'achat
                tpPrice = float(bitget.convert_price_to_precision(
                    symbol, buyPrice + TpPct * buyPrice))
                # Calculer la quantité d'achat en USD en fonction du solde en USD et du nombre maximum de positions ouvertes
                buyQuantityInUsd = usdBalance * 1 / \
                    (maxOpenPosition-openPositions)

                # Réduire la quantité d'achat de 5% si c'est la dernière position à ouvrir
                if openPositions == maxOpenPosition - 1:
                    buyQuantityInUsd = 0.95 * buyQuantityInUsd

                # Convertir la quantité d'achat en précision requise pour la paire de trading
                buyAmount = float(bitget.convert_amount_to_precision(symbol, float(
                    bitget.convert_amount_to_precision(
                        symbol, buyQuantityInUsd / buyPrice)
                )))
                # Afficher les valeurs de certains paramètres pour le débogage
                print("usdBalance:", usdBalance, "buyQuantityInUsd:", buyQuantityInUsd,
                      "buyAmount:", buyAmount, "buyPrice:", buyPrice, "openPositions:", openPositions)
                time.sleep(2)
                # Placer un ordre d'achat limité pour la quantité et le prix spécifiés, avec réduction désactivée
                buy = bitget.place_limit_order(
                    symbol, 'buy', buyAmount, buyPrice, reduce=False)
                # Ajouter un message à la liste des messages avec les détails de l'achat
                message_list.append(MESSAGE_TEMPLATE['message_buy'].format(
                    subAccountName, str(buyAmount), str(coin), str(buyPrice)))
                # Afficher un message indiquant que l'achat a été effectué
                print(f"Achat")
                # Incrémenter le nombre de positions ouvertes
                openPositions += 1

message_list.append(MESSAGE_TEMPLATE['message_wallet'].format(
    subAccountName, str(usdBalance)))

intents = discord.Intents.default()  # Crée un objet Intents avec les intentions par défaut
intents.typing = False  # Optionnel : désactive l'intention de voir lorsque quelqu'un tape un message
intents.presences = False  # Optionnel : désactive l'intention de voir les présences des utilisateurs
TOKEN = secret["discord_exemple"]["token"]
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    # join prend une list et à chaque élément de la list ajoute "\n" ou autre
    msg = "\n".join(message_list)
    id = int(secret["discord_exemple"]["channel"])
    channel = client.get_channel(id)
    await channel.send(msg)
    await client.close()
client.run(TOKEN)
