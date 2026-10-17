"""OKX TR çekim ağı adı → zincir anahtarı, okuyucu ve gezgin. Tabloda olmayan ağ katman 1'de kalır."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Ag:
    anahtar: str
    ad: str                      # ekranda
    evm_zincir: int | None       # Etherscan/Routescan chainId
    onchainos: str | None        # OnchainOS chainIndex
    gezgin: str | None           # adres bağlantısı tabanı
    yerel: str                   # yerel coin
    okuyucu: tuple[str, ...]     # sırayla denenecek okuyucular

    @property
    def katman(self) -> int:
        return 3 if self.okuyucu else 1


# Okuyucu sırası: bütün geçmiş gezginden; OnchainOS (OKX, yalnız son 6 ay) yedek, gezgini olmayan BNB/Base/OP'de tek okuyucu.
# Anahtar: OKX `chain` alanındaki ağ kısmı ("USDT-Arbitrum One" → "Arbitrum One")
AGLAR = {
    "ERC20": Ag("ethereum", "Ethereum", 1, "1", "https://etherscan.io/address/", "ETH", ("etherscan", "routescan", "onchainos")),
    "Arbitrum One": Ag("arbitrum", "Arbitrum", 42161, "42161", "https://arbiscan.io/address/", "ETH", ("etherscan", "onchainos")),
    "Polygon": Ag("polygon", "Polygon", 137, "137", "https://polygonscan.com/address/", "POL", ("etherscan", "onchainos")),
    "Avalanche C-Chain": Ag("avalanche", "Avalanche", 43114, "43114", "https://snowtrace.io/address/", "AVAX", ("routescan", "onchainos")),
    "Chiliz Chain": Ag("chiliz", "Chiliz", 88888, None, "https://chiliscan.com/address/", "CHZ", ("routescan",)),
    "TRC20": Ag("tron", "Tron", None, "195", "https://tronscan.org/#/address/", "TRX", ("trongrid", "onchainos")),
    "BSC": Ag("bnb", "BNB Chain", 56, "56", "https://bscscan.com/address/", "BNB", ("onchainos",)),
    "Base": Ag("base", "Base", 8453, "8453", "https://basescan.org/address/", "ETH", ("onchainos",)),
    "Optimism": Ag("optimism", "Optimism", 10, "10", "https://optimistic.etherscan.io/address/", "ETH", ("onchainos",)),
    "Solana": Ag("solana", "Solana", None, "501", "https://solscan.io/account/", "SOL", ()),  # 3. katman kesildi
}
TAKMA = {"BEP20": "BSC", "BNB Smart Chain": "BSC", "OPTIMISM": "Optimism", "Arbitrum": "Arbitrum One",
         "AVAX C-Chain": "Avalanche C-Chain", "Chiliz": "Chiliz Chain", "TRON": "TRC20"}


def ag_kismi(chain: str) -> str:
    """'USDT-Arbitrum One' → 'Arbitrum One'."""
    return chain.split("-", 1)[1] if "-" in chain else chain


def ag_bul(chain: str) -> Ag:
    kisim = ag_kismi(chain)
    kisim = TAKMA.get(kisim, kisim)
    if kisim in AGLAR:
        return AGLAR[kisim]
    anahtar = re.sub(r"[^a-z0-9]+", "-", kisim.lower()).strip("-") or "bilinmeyen"
    return Ag(anahtar, kisim, None, None, None, "", ())


def gezgin_url(ag: Ag, adres: str) -> str | None:
    return ag.gezgin + adres if ag.gezgin else None
