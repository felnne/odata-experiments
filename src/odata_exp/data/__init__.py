from datetime import datetime
from pathlib import Path
from typing import Dict, List

from geojson import load as geojson_load, FeatureCollection


def load_depots() -> FeatureCollection:
    with open(Path("src/odata_exp/data/depots.geojson"), mode="r") as file:
        return geojson_load(file)


def get_depots() -> List[Dict[str, str]]:
    feature_collection = load_depots()

    depots = []
    for feature in feature_collection["features"]:
        depots.append(
            {
                "identifier": feature["properties"]["identifier"],
                "latitude": feature["geometry"]["coordinates"][1],
                "longitude": feature["geometry"]["coordinates"][0],
                "established_at": datetime.fromisoformat(
                    feature["properties"]["established_at"]
                ).date(),
            }
        )

    return depots
