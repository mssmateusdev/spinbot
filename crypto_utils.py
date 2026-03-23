import requests
import time

COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=brl"

class CryptoConverter:
    _cached_price = 1000.0 # Valor seguro inicial caso falhe a rede
    _last_update = 0
    _update_interval = 1800 # 30 minutos

    @classmethod
    def get_sol_price(cls):
        now = time.time()
        if now - cls._last_update > cls._update_interval:
            try:
                response = requests.get(COINGECKO_API, timeout=5)
                data = response.json()
                cls._cached_price = data['solana']['brl']
                cls._last_update = now
            except:
                pass # Mantém o cache anterior
        return cls._cached_price

    @classmethod
    def coins_to_brl(cls, coins):
        if coins <= 0: return 0.0
        sol_price = cls.get_sol_price()
        # 10.000 Coins = 0.00006685 SOL
        sol_amount = (coins / 10000) * 0.00006685
        return sol_amount * sol_price
