import logging
import json
import urllib.request
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Cache of ID -> Official English Name from api.changes.tg
ID_TO_NAME: Dict[int, str] = {
    6046178578163303744: "Celebration Cake",
    5974210632977745012: "Teddy Bear",
    6026193266406327981: "Surprise Box",
    5969796561943660080: "Holiday Box",
    5935895822435615975: "Special Gift",
    5893356958802511476: "Golden Box",
    5866352046986232958: "Classic Bear",
    5800655655995968830: "Secret Gift",
    5801108895304779062: "Mystery Box",
    5956217000635139069: "Wonder Box",
    5922558454332916696: "Xmas Pine",
    5879737836550226478: "Mini Oscar",
    5882125812596999035: "Eternal Rose",
    5783075783622787539: "Homemade Cake",
    5868455043362980631: "Heart Locket",
    5868220813026526561: "Toy Bear",
    5170594532177215681: "Lol Pop",
    5871002671934079382: "Lush Bouquet",
    5868503709637411929: "Diamond Ring",
    6042113507581755979: "Stellar Rocket",
    5846226946928673709: "Magic Potion",
}

class CatalogService:
    @staticmethod
    def get_gift_title(gift_id: int) -> str:
        """
        Returns official English name from api.changes.tg or fallback to 'Gift #<id>'
        """
        if gift_id in ID_TO_NAME:
            return ID_TO_NAME[gift_id]
        return f"Gift #{gift_id}"

    @staticmethod
    async def sync_catalog_from_api():
        """
        Loads official English gift names from https://api.changes.tg/ids
        """
        global ID_TO_NAME
        api_url = "https://api.changes.tg/ids"
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "TelegramBot/1.0 (powered by @GiftChanges)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for gid_str, en_name in data.items():
                    ID_TO_NAME[int(gid_str)] = en_name.strip()
                logger.info(f"Loaded {len(ID_TO_NAME)} official English gift names from api.changes.tg")
        except Exception as e:
            logger.warning(f"Error fetching names from api.changes.tg: {e}")

catalog_service = CatalogService()
