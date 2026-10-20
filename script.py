%pip install -q geopandas folium mapclassify contextily "pandas<3" "numpy<2"
notebookutils.session.restartPython()

# ===================================

import notebookutils
import geopandas as gpd
from deltalake import DeltaTable
import matplotlib.pyplot as plt

contexte = notebookutils.runtime.context
endpoint = notebookutils.conf.get("trident.onelake.endpoint").replace("https://", "")
racine = f"abfss://{contexte['defaultLakehouseWorkspaceId']}@{endpoint}/{contexte['defaultLakehouseId']}"
acces = {"bearer_token": notebookutils.credentials.getToken("storage"), "use_fabric_endpoint": "true"}

df = DeltaTable(f"{racine}/Tables/dbo/carreaux", storage_options=acces).to_pandas()
car = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries.from_wkt(df["contour_wkt"]), crs=4326)

ax = car.plot(color="red", edgecolor="none", figsize=(10, 10))
ax.set_title("Carreaux habités — Toulouse Métropole")
ax.set_axis_off()
plt.show()

# ===================================

import json
import contextily as cx
import matplotlib.pyplot as plt
from shapely.geometry import shape

# Communes de la zone (table du data engineer)
zc = DeltaTable(f"{racine}/Tables/dbo/zone_communes", storage_options=acces).to_pandas()
com = gpd.GeoDataFrame(zc, geometry=[shape(json.loads(g)) for g in zc["contour_geojson"]], crs=4326)

# Projection des fonds de carte web
car_m = car.to_crs(3857)
com_m = com.to_crs(3857)

ax = car_m.plot(color="red", edgecolor="none", alpha=0.4, figsize=(14, 14))
com_m.boundary.plot(ax=ax, color="black", linewidth=0.8)
for _, c in com_m.iterrows():
    p = c.geometry.representative_point()
    ax.annotate(c["nom"], (p.x, p.y), fontsize=7, ha="center")

cx.add_basemap(ax, source=cx.providers.Esri.WorldStreetMap)
ax.set_title(f"Carreaux habités — Toulouse Métropole ({len(com)} communes)")
ax.set_axis_off()
plt.show()

# ===================================

import folium
import pandas as pd

def lire(nom):
    return DeltaTable(f"{racine}/Tables/dbo/{nom}", storage_options=acces).to_pandas()

# Arrêts de transport en commun de la zone
arrets = lire("arrets")
arrets = arrets[arrets["dans_zone"]]

# Stations partagées de la zone, Citiz séparé du reste
partagees = lire("stations_partagees")
partagees = partagees[partagees["dans_zone"]]
citiz = partagees[partagees["operateur"] == "Citiz"]
stations = partagees[partagees["operateur"] != "Citiz"]

# Détail du nombre de lignes par mode pour chaque arrêt (ex : "1 metro, 3 bus")
detail = (
    lire("arrets_lignes")
    .groupby(["arret_id", "mode"])["ligne_id"].nunique()
    .reset_index()
    .assign(txt=lambda d: d["ligne_id"].astype(str) + " " + d["mode"])
    .groupby("arret_id")["txt"].agg(", ".join)
)
arrets["detail_lignes"] = arrets["arret_id"].map(detail).fillna("")

# Un arrêt va dans chaque calque des modes qui le desservent
a_bus = arrets["modes"].str.contains("bus")
a_tram = arrets["modes"].str.contains("tram")
a_metro = arrets["modes"].str.contains("metro")
a_telepherique = arrets["modes"].str.contains("telepherique")
a_train = arrets["modes"].str.contains("train")

m = folium.Map(
    location=[arrets["lat"].mean(), arrets["lon"].mean()], zoom_start=12,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
)

def calque(df, nom, couleur, rayon, infobulle):
    groupe = folium.FeatureGroup(name=f"{nom} ({len(df)})")
    for _, r in df.iterrows():
        folium.CircleMarker(
            [r["lat"], r["lon"]], radius=rayon, color=couleur, fill=True, fill_opacity=0.8,
            weight=1, tooltip=infobulle(r),
        ).add_to(groupe)
    groupe.add_to(m)

infobulle_arret = lambda r: f"{r['nom']} — {r['reseau']} — {r['detail_lignes']}"

# Ordre de dessin : petits points d'abord, gros points par-dessus
calque(arrets[a_bus], "Arrêts bus", "blue", 3, infobulle_arret)
calque(arrets[a_tram], "Arrêts tram", "deeppink", 5, infobulle_arret)
calque(arrets[a_telepherique], "Téléphérique", "saddlebrown", 6, infobulle_arret)
calque(arrets[a_metro], "Stations métro", "purple", 6, infobulle_arret)
calque(arrets[a_train], "Gares", "red", 6, infobulle_arret)
calque(stations, "Stations vélo", "green", 4,
       lambda r: f"{r['nom']} — {r['operateur']} — {r['capacite']} places")
calque(citiz, "Stations Citiz", "orange", 7,
       lambda r: f"Citiz {r['nom']} — {r['capacite']} véhicules")

folium.LayerControl(collapsed=False).add_to(m)
display(m)

# ===================================

import numpy as np
import pandas as pd
import folium
import branca.colormap as bcm
from scipy.spatial import cKDTree

# ============ PARAMÈTRES (à modifier) ============
SEUIL = 50           # carreaux de moins de SEUIL habitants : pas de score, en gris
RAYON = 400           # 5 min à pied, en mètres
PLAFOND_PCT = 0.95    # l'échelle de couleur s'arrête au score atteint par 95 % des carreaux
# =================================================

# ---------- 1. Données ----------
# Tous les arrêts et stations, pas seulement ceux de la zone :
# un habitant en bordure peut marcher jusqu'à un arrêt de la commune voisine.
tous_arrets = lire("arrets")
toutes_stations = lire("stations_partagees")
arrets_lignes = lire("arrets_lignes")

centres = car[["x_3035", "y_3035"]].to_numpy()

def proches(points):
    """Pour chaque carreau, la liste des points situés à moins de RAYON mètres de son centre."""
    arbre = cKDTree(points[["x_3035", "y_3035"]].to_numpy())
    return arbre.query_ball_point(centres, r=RAYON)

# ---------- 2. Options à moins de 400 m ----------
# Lignes de transport en commun distinctes (une ligne avec 3 arrêts proches = 1 option)
couples = pd.DataFrame({"idcar_200m": car["idcar_200m"].to_numpy(),
                        "idx": proches(tous_arrets)}).explode("idx").dropna()
couples["arret_id"] = tous_arrets["arret_id"].to_numpy()[couples["idx"].astype(int)]
lignes = couples.merge(arrets_lignes[["arret_id", "ligne_id"]], on="arret_id")
nb_lignes = lignes.groupby("idcar_200m")["ligne_id"].nunique()
car["nb_lignes"] = car["idcar_200m"].map(nb_lignes).fillna(0).astype(int)

# Stations vélo et Citiz
velo = toutes_stations[toutes_stations["operateur"] != "Citiz"]
cz = toutes_stations[toutes_stations["operateur"] == "Citiz"]
car["nb_velo"] = [len(v) for v in proches(velo)]
car["nb_citiz"] = [len(v) for v in proches(cz)]

car["options"] = car["nb_lignes"] + car["nb_velo"] + car["nb_citiz"]

# ---------- 3. Score ----------
car["grise"] = car["population"] < SEUIL
car["options_1000_hab"] = (car["options"] / car["population"] * 1000).round(1).where(~car["grise"])

# ---------- 4. Chiffres de contrôle ----------
pop_totale = car["population"].sum()
print("Effet de différents seuils (pour info) :")
print(pd.DataFrame([{
    "seuil": s,
    "carreaux_grises": int((car["population"] < s).sum()),
    "pct_population_grisee": round(car.loc[car["population"] < s, "population"].sum() / pop_totale * 100, 1),
} for s in [10, 20, 50, 100, SEUIL]]).drop_duplicates().sort_values("seuil").to_string(index=False))

grise_pop = car.loc[car["grise"], "population"].sum()
sans = car["options"] == 0
print(f"\nSeuil utilisé : {SEUIL} hab. -> {int(car['grise'].sum())} carreaux gris, {grise_pop / pop_totale:.1%} de la population")
print(f"Habitants sans aucune option à 5 min : {car.loc[sans, 'population'].sum():,.0f} "
      f"({car.loc[sans, 'population'].sum() / pop_totale:.1%})")

# ---------- 5. Carte ----------
DEGRADE = ["#d1e5f0", "#92c5de", "#ffffbf", "#fdae61", "#f46d43", "#a50026"]  # du froid au chaud
GRIS = "#bdbdbd"

calcule = ~car["grise"]
score = car.loc[calcule, "options_1000_hab"]

# Dégradé régulier de 0 au plafond ; au-dessus = couleur la plus chaude (valeur réelle dans l'info-bulle)
PLAFOND = max(round(score.quantile(PLAFOND_PCT)), 1)
echelle = bcm.LinearColormap(DEGRADE, vmin=0, vmax=PLAFOND)
car["couleur"] = GRIS
car.loc[calcule, "couleur"] = score.clip(upper=PLAFOND).map(echelle)
print(f"Échelle de couleur : 0 à {PLAFOND} ; {(score > PLAFOND).sum()} carreaux au-dessus")

car["score_txt"] = car["options_1000_hab"].map(lambda v: "pas de score (peu d'habitants)" if pd.isna(v) else f"{v:g}")

champs = ["idcar_200m", "score_txt", "population", "options", "nb_citiz"]
alias = ["Carreau", "Score", "Habitants", "Options disponibles", "Dont Citiz"]

m = folium.Map(
    location=[car["lat"].mean(), car["lon"].mean()], zoom_start=12,
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
)

folium.GeoJson(
    car[champs + ["couleur", "geometry"]].to_json(),
    name="Score d'accès",
    style_function=lambda f: {"fillColor": f["properties"]["couleur"], "weight": 0, "fillOpacity": 0.7},
    tooltip=folium.GeoJsonTooltip(fields=champs, aliases=alias),
).add_to(m)

# Légende : barre de dégradé avec graduations régulières
graduations = np.linspace(0, PLAFOND, 5).round().astype(int)
etiquettes = "".join(f"<span>{v}</span>" for v in graduations[:-1]) + f"<span>{PLAFOND} et +</span>"
html = f"""<div style="position:fixed;bottom:20px;left:20px;z-index:9999;background:white;padding:10px;
font-size:12px;border:1px solid #999;border-radius:4px;width:260px">
<b>Options pour 1 000 habitants</b>
<div style="height:14px;margin:6px 0 2px;background:linear-gradient(to right,{','.join(DEGRADE)})"></div>
<div style="display:flex;justify-content:space-between">{etiquettes}</div>
<div style="margin-top:6px"><span style="background:{GRIS};width:14px;height:14px;display:inline-block;margin-right:6px;vertical-align:middle"></span>pas de score (moins de {SEUIL} habitants)</div>
</div>"""
m.get_root().html.add_child(folium.Element(html))

display(m)
